"""Vision Analyst agent: analyze photo to identify item and problem."""
from __future__ import annotations
import logging
from src.models.schemas import IssueAnalysis
from src.utils.config import load_prompt
from src.utils.llm import llm_vision_json

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM = """You are a home maintenance expert analyzing a photo. Describe exactly what you see:
1. What item is shown? Be specific (e.g., "A19 light bulb", "garage door panel", "kitchen faucet handle").
2. What is wrong with it? Be specific (e.g., "burned out", "cracked along the left edge", "rusted at the base").
3. Read any visible text: brand names, model numbers, wattage, voltage, size markings.
4. Describe the physical characteristics: shape, color, size, material, base/connector type.
5. How difficult is this repair? Rate 1-5: 1=trivial (swap a bulb), 2=easy (basic tools, 10-30 min), 3=moderate (DIY skill, 30-60 min), 4=hard (1-2 people, half day), 5=professional (hire a pro).
6. What tools are needed? List specific tools.
7. Write a brief step-by-step fix plan (fix_summary).
8. Set diy_or_hire to "diy", "either", or "hire" based on whether a typical homeowner can handle this safely.
9. If hiring is recommended, explain why (hire_reason) and estimate handyman labor cost as a range in cents (e.g. $80 = 8000).

Rules:
- Only report what is VISIBLE. Do not guess text you cannot read.
- If the image is blurry or unclear, say so and set confidence low.
- Do not recommend products. Only describe what you see.
- item_category should be a short, specific description of the item, NOT "other".
- problem_type should describe the actual problem, NOT "other".

Return JSON: {"item_category": "string", "problem_type": "string", "visible_brand": "string or null", "visible_model": "string or null", "visible_text": ["string"], "description": "string", "confidence": 0.0, "difficulty_score": 1, "difficulty_summary": "string", "required_tools": ["string"], "fix_summary": "string", "diy_or_hire": "diy|either|hire", "hire_reason": "string", "hire_price_min_cents": 0, "hire_price_max_cents": 0}"""


def analyze(photo_path: str, session_id: str, user_description: str = "",
            encoded: tuple[str, str] | None = None) -> IssueAnalysis:
    """Analyze a photo and return an IssueAnalysis."""
    system = load_prompt("vision_analyst") or _DEFAULT_SYSTEM
    user_text = "Analyze this photo of a home maintenance issue."
    if user_description:
        user_text += f"\n\nUser description: {user_description}"

    try:
        result = llm_vision_json(system, user_text, photo_path, _encoded=encoded)
        return IssueAnalysis(
            session_id=session_id,
            item_category=result.get("item_category", "other"),
            problem_type=result.get("problem_type", "unknown"),
            visible_brand=result.get("visible_brand"),
            visible_model=result.get("visible_model"),
            visible_text=result.get("visible_text", []),
            description=result.get("description", ""),
            confidence=float(result.get("confidence", 0.5)),
            difficulty_score=int(result.get("difficulty_score", 1)),
            difficulty_summary=result.get("difficulty_summary", ""),
            required_tools=result.get("required_tools", []),
            fix_summary=result.get("fix_summary", ""),
            diy_or_hire=result.get("diy_or_hire", ""),
            hire_reason=result.get("hire_reason", ""),
            hire_price_min_cents=int(result.get("hire_price_min_cents", 0)),
            hire_price_max_cents=int(result.get("hire_price_max_cents", 0)),
        )
    except Exception as e:
        logger.error("Vision analysis failed: %s", e)
        return IssueAnalysis(session_id=session_id, description=f"Analysis failed: {e}", confidence=0.0)
