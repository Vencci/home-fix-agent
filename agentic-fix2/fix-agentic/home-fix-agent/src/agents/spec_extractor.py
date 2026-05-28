"""Spec Extractor agent: determine replacement product specifications."""
from __future__ import annotations
import logging
from src.models.schemas import IssueAnalysis, ProductSpec
from src.utils.config import load_prompt
from src.utils.llm import llm_vision_json

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM = """You are a product specification expert. Given a photo and an issue analysis of a home item, determine the exact replacement product specifications.

For a light bulb: base_type, wattage_equivalent, color_temperature_k, shape, technology, dimmable.
For a battery: size, chemistry, voltage.
For a filter: length_inches, width_inches, depth_inches, merv_rating.
For hardware: item_type, size, material, color_finish.

Rules:
- Use visible text as primary evidence.
- Infer from physical characteristics when text is not visible.
- Set confidence per field (0-1). If guessing, confidence must be below 0.7.
- Generate clarification_questions for any critical field with confidence below 0.7.
- Generate a search_query string suitable for searching a shopping site.
- If "Additional info from user" contains prior specs and user feedback, UPDATE the specs accordingly. The user's explicit preferences override inferred values. Increase confidence to 1.0 for any field the user has explicitly confirmed or specified.
- When user feedback mentions preferences (e.g., "dimmable", "cheaper", "LED", "brand X"), incorporate them into attributes AND search_query.

Return JSON: {"item_category": "string", "attributes": {}, "confidence_per_field": {}, "clarification_questions": ["string"], "search_query": "string"}"""


def extract(analysis: IssueAnalysis, photo_path: str, extra_context: str = "") -> ProductSpec:
    """Extract product specs from analysis + photo."""
    system = load_prompt("spec_extractor") or _DEFAULT_SYSTEM
    user_text = (
        f"Item: {analysis.item_category}\n"
        f"Problem: {analysis.problem_type}\n"
        f"Visible text: {', '.join(analysis.visible_text)}\n"
        f"Description: {analysis.description}"
    )
    if analysis.visible_brand:
        user_text += f"\nBrand: {analysis.visible_brand}"
    if extra_context:
        user_text += f"\nAdditional info from user: {extra_context}"

    try:
        result = llm_vision_json(system, user_text, photo_path)
        return ProductSpec(
            session_id=analysis.session_id,
            item_category=result.get("item_category", analysis.item_category),
            attributes=result.get("attributes", {}),
            confidence_per_field=result.get("confidence_per_field", {}),
            clarification_questions=result.get("clarification_questions", []),
            search_query=result.get("search_query", ""),
        )
    except Exception as e:
        logger.error("Spec extraction failed: %s", e)
        return ProductSpec(session_id=analysis.session_id, item_category=analysis.item_category)
