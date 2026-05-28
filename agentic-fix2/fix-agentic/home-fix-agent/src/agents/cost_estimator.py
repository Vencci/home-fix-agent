"""Cost Estimator agent: estimate total repair cost (parts + tools + labor)."""
from __future__ import annotations
import logging
from src.models.schemas import CostEstimate, IssueAnalysis, ProductResult
from src.utils.llm import llm_json

logger = logging.getLogger(__name__)

_SYSTEM = """You are a home repair cost estimator. Given a repair analysis and product options, estimate the full cost of the repair.

Return JSON:
{
  "tool_details": [{"name": "string", "price_low_cents": int, "price_high_cents": int, "likely_owned": bool}],
  "assumes_own_tools": bool,
  "summary": "string"
}

Rules:
- tool_details: for each required tool, estimate retail price range in cents. Set likely_owned=true for common household tools (screwdriver, hammer, etc.).
- assumes_own_tools: true if most tools are common and likely already owned.
- summary: one sentence describing total cost outlook (e.g., "Simple $5 bulb swap — no extra tools needed" or "Expect $150-300 total including parts, a new caulk gun, and optional labor").
- price_low_cents and price_high_cents must be in cents (e.g., $12.99 = 1299).
- Be realistic with tool prices based on typical hardware store prices."""


def estimate(analysis: IssueAnalysis, products: list[ProductResult]) -> CostEstimate:
    """Estimate full repair cost from analysis and top product results."""
    if not products:
        return CostEstimate(summary="No products found to estimate cost.")

    parts_low = min(p.price_cents for p in products)
    parts_high = max(p.price_cents for p in products)

    labor_low = analysis.hire_price_min_cents
    labor_high = analysis.hire_price_max_cents

    tools = analysis.required_tools
    if not tools:
        total_low = parts_low + labor_low
        total_high = parts_high + labor_high
        return CostEstimate(
            parts_low_cents=parts_low,
            parts_high_cents=parts_high,
            labor_low_cents=labor_low,
            labor_high_cents=labor_high,
            total_low_cents=total_low,
            total_high_cents=total_high,
            assumes_own_tools=True,
            summary=_quick_summary(parts_low, parts_high, 0, 0, labor_low, labor_high, analysis.diy_or_hire),
        )

    try:
        result = llm_json(
            _SYSTEM,
            f"Item: {analysis.item_category}\n"
            f"Problem: {analysis.problem_type}\n"
            f"Difficulty: {analysis.difficulty_score}/5\n"
            f"Required tools: {', '.join(tools)}\n"
            f"Parts price range: ${parts_low/100:.2f} - ${parts_high/100:.2f}\n"
            f"DIY or hire: {analysis.diy_or_hire}",
        )

        tool_details = result.get("tool_details", [])
        assumes_own = result.get("assumes_own_tools", False)

        tools_low = 0
        tools_high = 0
        if not assumes_own:
            for t in tool_details:
                if not t.get("likely_owned", False):
                    tools_low += t.get("price_low_cents", 0)
                    tools_high += t.get("price_high_cents", 0)

        total_low = parts_low + tools_low + labor_low
        total_high = parts_high + tools_high + labor_high

        summary = result.get("summary", "") or _quick_summary(
            parts_low, parts_high, tools_low, tools_high, labor_low, labor_high, analysis.diy_or_hire
        )

        return CostEstimate(
            parts_low_cents=parts_low,
            parts_high_cents=parts_high,
            tools_low_cents=tools_low,
            tools_high_cents=tools_high,
            labor_low_cents=labor_low,
            labor_high_cents=labor_high,
            total_low_cents=total_low,
            total_high_cents=total_high,
            tool_details=tool_details,
            assumes_own_tools=assumes_own,
            summary=summary,
        )
    except Exception as e:
        logger.warning("Cost estimation LLM call failed: %s", e)
        total_low = parts_low + labor_low
        total_high = parts_high + labor_high
        return CostEstimate(
            parts_low_cents=parts_low,
            parts_high_cents=parts_high,
            labor_low_cents=labor_low,
            labor_high_cents=labor_high,
            total_low_cents=total_low,
            total_high_cents=total_high,
            assumes_own_tools=True,
            summary=_quick_summary(parts_low, parts_high, 0, 0, labor_low, labor_high, analysis.diy_or_hire),
        )


def _quick_summary(parts_lo, parts_hi, tools_lo, tools_hi, labor_lo, labor_hi, diy_or_hire):
    def fmt(cents):
        return f"${cents / 100:.0f}" if cents >= 100 else f"${cents / 100:.2f}"

    parts = f"{fmt(parts_lo)}-{fmt(parts_hi)}" if parts_lo != parts_hi else fmt(parts_lo)
    pieces = [f"Parts: {parts}"]
    if tools_hi > 0:
        pieces.append(f"Tools: {fmt(tools_lo)}-{fmt(tools_hi)}")
    if labor_hi > 0 and diy_or_hire != "diy":
        pieces.append(f"Labor (optional): {fmt(labor_lo)}-{fmt(labor_hi)}")
    return " · ".join(pieces)
