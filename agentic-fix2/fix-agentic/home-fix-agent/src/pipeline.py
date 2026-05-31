"""Incremental pipeline: advances one stage at a time."""
from __future__ import annotations
import logging

from src.agents import cost_estimator, product_ranker, product_searcher, spec_extractor, vision_analyst
from src.models.schemas import (
    ChatMessage, ChatRole, PartSearchResult, PipelineResult, PipelineStage,
    ProductSpec, Session, SessionStatus,
)
from src.storage.store import save_result
from src.utils.llm import encode_image

logger = logging.getLogger(__name__)


def _msg(role: ChatRole, content: str, stage: str | None = None) -> ChatMessage:
    return ChatMessage(role=role, content=content, stage=stage)


def start_session(photo_path: str, description: str = "", session_id: str | None = None) -> PipelineResult:
    """Create session and run through analysis + spec extraction, blocking if clarification needed."""
    session = Session(description=description)
    if session_id:
        session.session_id = session_id
    result = PipelineResult(session=session, stage=PipelineStage.UPLOAD)
    session.photo_path = photo_path

    if description:
        result.messages.append(_msg(ChatRole.USER, description, "upload"))

    encoded = encode_image(photo_path)

    # Run analysis
    result = _run_analysis(result, encoded)
    if result.stage == PipelineStage.ERROR:
        save_result(result)
        return result

    # Run spec extraction + search (clarification questions shown alongside results)
    result = _run_spec_extraction(result, encoded=encoded)
    result = _run_part_searches(result)
    save_result(result)
    return result


def advance(result: PipelineResult, user_message: str) -> PipelineResult:
    """Advance the pipeline based on current stage and user input."""
    result.messages.append(_msg(ChatRole.USER, user_message, result.stage.value))

    if result.stage in (PipelineStage.RESULTS, PipelineStage.REFINING, PipelineStage.ERROR):
        # User is answering clarification or refining — re-search with their feedback
        result = _run_refinement(result, user_message)

    save_result(result)
    return result


def _run_analysis(result: PipelineResult, encoded: tuple[str, str] | None = None) -> PipelineResult:
    """Run vision analysis."""
    result.stage = PipelineStage.ANALYZING

    photo = result.session.photo_path
    sid = result.session.session_id
    desc = result.session.description

    analysis = vision_analyst.analyze(photo, sid, desc, encoded=encoded)
    result.analysis = analysis

    if analysis.confidence == 0.0:
        result.error = analysis.description or "Photo analysis failed. Try a clearer photo."
        result.stage = PipelineStage.ERROR
        result.messages.append(_msg(ChatRole.ASSISTANT, result.error, "error"))
        return result

    return result


def _run_spec_extraction(result: PipelineResult, extra_context: str = "",
                         encoded: tuple[str, str] | None = None) -> PipelineResult:
    """Run spec extraction. Shows clarification questions but proceeds to search regardless."""
    photo = result.session.photo_path
    spec = spec_extractor.extract(result.analysis, photo, extra_context, encoded=encoded)
    result.spec = spec
    return _run_search(result)


def _run_search(result: PipelineResult) -> PipelineResult:
    """Search for products and rank them."""
    result.stage = PipelineStage.SEARCHING
    result.products = []  # clear before searching so stale results never silently persist

    products = product_searcher.search(result.spec)
    if not products:
        result.error = "No products found. Try describing what you need."
        result.stage = PipelineStage.ERROR
        result.messages.append(_msg(ChatRole.ASSISTANT, result.error, "error"))
        return result

    result.products = product_ranker.rank(products, result.spec)[:5]
    result.stage = PipelineStage.RESULTS
    result.session.status = SessionStatus.COMPLETED

    # Estimate full repair cost
    if result.analysis:
        result.cost_estimate = cost_estimator.estimate(
            result.analysis, result.products,
            part_searches=result.part_searches or None,
        )

    return result


def _run_refinement(result: PipelineResult, feedback: str) -> PipelineResult:
    """Re-run spec extraction with accumulated user feedback, then re-search."""
    result.stage = PipelineStage.REFINING

    # Save current spec snapshot before overwriting
    if result.spec:
        result.spec_history.append({
            "attributes": dict(result.spec.attributes),
            "search_query": result.spec.search_query,
        })

    # Accumulate feedback across rounds
    result.refinement_history.append(feedback)

    # Build full context from all prior feedback + current spec
    context_parts = []
    if result.spec:
        context_parts.append(f"Current specs: {result.spec.attributes}")
        context_parts.append(f"Current search query: {result.spec.search_query}")
    for i, fb in enumerate(result.refinement_history, 1):
        context_parts.append(f"User feedback round {i}: {fb}")
    extra_context = "\n".join(context_parts)

    # Re-encode the photo so spec extractor has full image context during refinement
    encoded = None
    if result.session.photo_path:
        try:
            encoded = encode_image(result.session.photo_path)
        except Exception as exc:
            logger.warning("Could not re-encode photo for refinement: %s", exc)

    result = _run_spec_extraction(result, extra_context=extra_context, encoded=encoded)
    result = _run_part_searches(result)

    # Show what changed
    if result.spec and result.spec_history:
        prev = result.spec_history[-1]
        changes = _diff_specs(prev["attributes"], result.spec.attributes)
        if changes:
            change_lines = "\n".join(f"- **{k}**: {old} → {new}" for k, old, new in changes)
            result.messages.append(_msg(
                ChatRole.ASSISTANT,
                f"Updated specs based on your feedback:\n\n{change_lines}",
                "refining",
            ))
        if prev["search_query"] != result.spec.search_query:
            result.messages.append(_msg(
                ChatRole.SYSTEM,
                f"Search updated: {result.spec.search_query}",
                "refining",
            ))

    return result


def stream_session(photo_path: str, description: str = "", session_id: str | None = None):
    """Generator that yields (event_type, PipelineResult) as each stage completes.

    Yields: "analysis", "spec", "products", "done", or "error".
    """
    session = Session(description=description)
    if session_id:
        session.session_id = session_id
    result = PipelineResult(session=session, stage=PipelineStage.UPLOAD)
    session.photo_path = photo_path

    if description:
        result.messages.append(_msg(ChatRole.USER, description, "upload"))

    encoded = encode_image(photo_path)

    result = _run_analysis(result, encoded)
    if result.stage == PipelineStage.ERROR:
        save_result(result)
        yield "error", result
        return

    yield "analysis", result

    photo = result.session.photo_path
    result.spec = spec_extractor.extract(result.analysis, photo, encoded=encoded)
    yield "spec", result

    result = _run_search(result)
    if result.stage == PipelineStage.ERROR:
        save_result(result)
        yield "error", result
        return

    result = _run_part_searches(result)
    yield "products", result

    if result.analysis:
        all_products = (
            [p for ps in result.part_searches for p in ps.products]
            if result.part_searches else result.products
        )
        result.cost_estimate = cost_estimator.estimate(result.analysis, result.products,
                                                       part_searches=result.part_searches or None)

    save_result(result)
    yield "done", result


def _run_part_searches(result: PipelineResult) -> PipelineResult:
    """If the analysis identified multiple purchasable parts, search for each one."""
    parts = (result.analysis.parts_to_purchase or []) if result.analysis else []
    if len(parts) <= 1:
        return result  # single-part: main _run_search already handled it

    result.part_searches = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        name = part.get("name", "").strip()
        desc = part.get("description", "").strip()
        sq = part.get("search_query", "").strip() or f"{name} {desc}".strip()
        if not name:
            continue

        part_spec = ProductSpec(
            session_id=result.session.session_id,
            item_category=name,
            search_query=sq,
            attributes={"name": name, "description": desc},
        )
        try:
            products = product_searcher.search(part_spec)
            ranked = product_ranker.rank(products, part_spec)[:3] if products else []
        except Exception as exc:
            logger.warning("Part search failed for '%s': %s", name, exc)
            ranked = []
        result.part_searches.append(PartSearchResult(
            part_name=name,
            part_description=desc,
            search_query=sq,
            products=ranked,
        ))

    return result


def _diff_specs(old: dict, new: dict) -> list[tuple[str, str, str]]:
    """Return list of (key, old_value, new_value) for changed or added fields."""
    changes = []
    all_keys = set(old) | set(new)
    for k in sorted(all_keys):
        old_v = str(old.get(k, "—"))
        new_v = str(new.get(k, "—"))
        if old_v != new_v:
            changes.append((k.replace("_", " "), old_v, new_v))
    return changes
