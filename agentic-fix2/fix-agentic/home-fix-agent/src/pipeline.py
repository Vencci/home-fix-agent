"""Incremental pipeline: advances one stage at a time."""
from __future__ import annotations
import logging

from src.agents import cost_estimator, product_ranker, product_searcher, spec_extractor, vision_analyst
from src.models.schemas import (
    ChatMessage, ChatRole, PipelineResult, PipelineStage, Session, SessionStatus,
)
from src.storage.store import save_result

logger = logging.getLogger(__name__)


def _msg(role: ChatRole, content: str, stage: str | None = None) -> ChatMessage:
    return ChatMessage(role=role, content=content, stage=stage)


def start_session(photo_path: str, description: str = "") -> PipelineResult:
    """Create session and run through analysis + spec extraction, blocking if clarification needed."""
    session = Session(description=description)
    result = PipelineResult(session=session, stage=PipelineStage.UPLOAD)
    session.photo_path = photo_path

    if description:
        result.messages.append(_msg(ChatRole.USER, description, "upload"))

    # Run analysis
    result = _run_analysis(result)
    if result.stage == PipelineStage.ERROR:
        save_result(result)
        return result

    # Run spec extraction + search (clarification questions shown alongside results)
    result = _run_spec_extraction(result)
    save_result(result)
    return result


def advance(result: PipelineResult, user_message: str) -> PipelineResult:
    """Advance the pipeline based on current stage and user input."""
    result.messages.append(_msg(ChatRole.USER, user_message, result.stage.value))

    if result.stage == PipelineStage.RESULTS:
        # User is answering clarification or refining — re-search with their feedback
        result = _run_refinement(result, user_message)

    save_result(result)
    return result


def _run_analysis(result: PipelineResult) -> PipelineResult:
    """Run vision analysis."""
    result.stage = PipelineStage.ANALYZING
    result.messages.append(_msg(ChatRole.SYSTEM, "Analyzing your photo...", "analyzing"))

    photo = result.session.photo_path
    sid = result.session.session_id
    desc = result.session.description

    analysis = vision_analyst.analyze(photo, sid, desc)
    result.analysis = analysis

    if analysis.confidence == 0.0:
        result.error = analysis.description or "Photo analysis failed. Try a clearer photo."
        result.stage = PipelineStage.ERROR
        result.messages.append(_msg(ChatRole.ASSISTANT, result.error, "error"))
        return result

    conf_pct = f"{analysis.confidence:.0%}"
    result.messages.append(_msg(
        ChatRole.ASSISTANT,
        f"Identified: **{analysis.item_category}** — {analysis.problem_type} ({conf_pct} confidence)\n\n{analysis.description}",
        "analyzing",
    ))
    return result


def _run_spec_extraction(result: PipelineResult, extra_context: str = "") -> PipelineResult:
    """Run spec extraction. Shows clarification questions but proceeds to search regardless."""
    photo = result.session.photo_path
    spec = spec_extractor.extract(result.analysis, photo, extra_context)
    result.spec = spec

    # Show clarification questions as suggestions, but don't block
    if spec.clarification_questions:
        questions = "\n".join(f"- {q}" for q in spec.clarification_questions)
        result.messages.append(_msg(
            ChatRole.ASSISTANT,
            f"I'm searching with best-effort specs. To improve results, you can answer:\n\n{questions}",
            "clarifying",
        ))

    return _run_search(result)


def _run_search(result: PipelineResult) -> PipelineResult:
    """Search for products and rank them."""
    result.stage = PipelineStage.SEARCHING
    result.messages.append(_msg(ChatRole.SYSTEM, f"Searching for: {result.spec.search_query}", "searching"))

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
        result.cost_estimate = cost_estimator.estimate(result.analysis, result.products)

    result.messages.append(_msg(
        ChatRole.ASSISTANT,
        f"Found {len(result.products)} products. You can select one to order, or tell me if you'd like something different (e.g. \"I need dimmable\" or \"show me cheaper options\").",
        "results",
    ))
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

    result = _run_spec_extraction(result, extra_context=extra_context)

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
