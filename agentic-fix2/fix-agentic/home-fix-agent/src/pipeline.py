"""Incremental pipeline: advances one stage at a time."""
from __future__ import annotations
import logging

from src.agents import cost_estimator, product_ranker, product_searcher, spec_extractor, vision_analyst
from src.models.schemas import (
    ChatMessage, ChatRole, PartSearchResult, PipelineResult, PipelineStage,
    ProductSpec, Session, SessionStatus,
)
from src.storage.store import save_result
from src.utils.llm import encode_image, llm_text

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

    if result.stage in (PipelineStage.RESULTS, PipelineStage.REFINING, PipelineStage.ERROR, PipelineStage.DONE):
        if _is_question(result, user_message):
            answer = _answer_question(result, user_message)
            result.messages.append(_msg(ChatRole.ASSISTANT, answer, "answering"))
        else:
            result = _run_refinement(result, user_message)

    save_result(result)
    return result


_INTENT_SYSTEM = """You help classify user messages in a home repair product recommendation app.

The user has already received product recommendations. Classify their message:

- QUESTION: asking for information ABOUT the current products or repair
  (e.g. "which has best reviews?", "what's the difference between #1 and #2?",
   "how do I install this?", "is this compatible with my model?", "what warranty does it have?")

- REFINE: asking for DIFFERENT or MODIFIED product recommendations
  (e.g. "show me cheaper ones", "I need a dimmable version", "find something from Amazon",
   "I want a black one", "show me options under $30", "find me brand X")

Respond with ONLY the word QUESTION or REFINE."""


def _is_question(result: PipelineResult, message: str) -> bool:
    """Return True if the message is a question about current results, not a refinement request."""
    if not result.products:
        return False
    products_preview = "; ".join(
        f"{i+1}. {p.title} ${p.price_cents/100:.0f}"
        for i, p in enumerate(result.products[:3])
    )
    context = (
        f"Item being repaired: {result.analysis.item_category if result.analysis else 'unknown'}\n"
        f"Current recommendations: {products_preview}\n"
        f"User message: {message}"
    )
    try:
        verdict = llm_text(_INTENT_SYSTEM, context, retries=0).strip().upper()
        logger.info("Intent classification: %r → %s", message[:60], verdict)
        return verdict == "QUESTION"
    except Exception as e:
        logger.warning("Intent classification failed: %s", e)
        return False  # default to refinement


_ANSWER_SYSTEM = """You are a helpful home repair assistant. The user has received product recommendations
and is asking a question about them or about the repair. Answer concisely and helpfully in 1-3 sentences.
Do not suggest doing another product search. Stick to answering what they asked."""


def _answer_question(result: PipelineResult, question: str) -> str:
    """Generate a conversational answer to a question about the current products/repair."""
    products_detail = "\n".join(
        f"{i+1}. {p.title} — ${p.price_cents/100:.2f}, {p.rating}★ ({p.review_count} reviews). {p.recommendation_reason}"
        for i, p in enumerate(result.products[:5])
    )
    analysis_ctx = ""
    if result.analysis:
        analysis_ctx = (
            f"Item: {result.analysis.item_category}\n"
            f"Problem: {result.analysis.problem_type}\n"
            f"Difficulty: {result.analysis.difficulty_summary}\n"
        )
    context = f"{analysis_ctx}\nCurrent product recommendations:\n{products_detail}\n\nUser question: {question}"
    try:
        return llm_text(_ANSWER_SYSTEM, context, retries=1)
    except Exception as e:
        logger.warning("Question answering failed: %s", e)
        return "Sorry, I couldn't answer that right now. Try rephrasing your question."


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

    # Build directive context so the spec extractor always updates the search_query
    context_parts = []
    if result.spec:
        context_parts.append(f"Current specs: {result.spec.attributes}")
        context_parts.append(f"Current search query (must be updated to match the user's new request): {result.spec.search_query}")
    if len(result.refinement_history) > 1:
        for i, fb in enumerate(result.refinement_history[:-1], 1):
            context_parts.append(f"Previous user request {i}: {fb}")
    context_parts.append(f"NEW USER REQUEST (highest priority — update search_query to reflect this): {feedback}")
    context_parts.append("IMPORTANT: You MUST produce a new search_query that incorporates the user's latest request. Do not return the same search_query as before.")
    extra_context = "\n".join(context_parts)

    # Re-encode the photo so spec extractor has full image context during refinement
    encoded = None
    if result.session.photo_path:
        try:
            encoded = encode_image(result.session.photo_path)
        except Exception as exc:
            logger.warning("Could not re-encode photo for refinement: %s", exc)

    prev_query = result.spec.search_query if result.spec else ""

    result = _run_spec_extraction(result, extra_context=extra_context, encoded=encoded)

    # If the LLM returned the same search_query, force-inject the user's key terms
    if result.spec and result.spec.search_query == prev_query and feedback.strip():
        stop_words = {'want', 'need', 'like', 'please', 'with', 'that', 'this', 'the', 'and',
                      'or', 'a', 'an', 'to', 'for', 'my', 'me', 'can', 'you', 'have', 'i'}
        key_terms = [w for w in feedback.lower().split() if len(w) >= 3 and w not in stop_words]
        if key_terms:
            result.spec.search_query = f"{prev_query} {' '.join(key_terms[:3])}".strip()
            logger.info("search_query unchanged by LLM; appended feedback terms: %s", result.spec.search_query)

    result = _run_part_searches(result)

    # Build a single clear assistant response summarising what happened
    search_query = result.spec.search_query if result.spec else "…"
    n_products = len(result.products)

    # Spec changes (optional detail)
    spec_change_text = ""
    if result.spec and result.spec_history:
        prev = result.spec_history[-1]
        changes = _diff_specs(prev["attributes"], result.spec.attributes)
        if changes:
            change_lines = ", ".join(f"**{k}** → {new}" for k, _, new in changes)
            spec_change_text = f" Updated specs: {change_lines}."

    if n_products:
        reply = (
            f"Found **{n_products} product{'s' if n_products != 1 else ''}** for "
            f"*{search_query}*.{spec_change_text} "
            f"The recommendations below have been updated."
        )
    else:
        reply = (
            f"Searched for *{search_query}* but found no matching products.{spec_change_text} "
            f"Try rephrasing or broadening your request."
        )

    result.messages.append(_msg(ChatRole.ASSISTANT, reply, "refining"))
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
