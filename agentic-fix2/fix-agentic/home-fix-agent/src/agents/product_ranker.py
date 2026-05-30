"""Product Ranker: score and rank search results."""
from __future__ import annotations
from src.models.schemas import ProductResult, ProductSpec
from src.utils.config import load_ranking

_ranking_cfg: dict | None = None

def _get_ranking() -> dict:
    global _ranking_cfg
    if _ranking_cfg is None:
        _ranking_cfg = load_ranking()
    return _ranking_cfg

_DEFAULT_WEIGHTS = {
    "spec_match": 0.40,
    "rating": 0.20,
    "price": 0.20,
    "availability": 0.10,
    "review_count": 0.10,
}


def _normalize(values: list[float], invert: bool = False) -> list[float]:
    """Min-max normalize a list of values to 0-1. Invert for 'lower is better'."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0] * len(values)
    normed = [(v - lo) / (hi - lo) for v in values]
    return [1.0 - n for n in normed] if invert else normed


def rank(products: list[ProductResult], spec: ProductSpec) -> list[ProductResult]:
    """Score and rank products. Returns sorted list with match_score and reason filled in."""
    if not products:
        return []

    cfg = _get_ranking()
    w = cfg.get("weights", _DEFAULT_WEIGHTS)

    # Normalize price (lower = better) and rating/reviews (higher = better)
    prices = _normalize([p.price_cents for p in products], invert=True)
    ratings = _normalize([p.rating for p in products])
    reviews = _normalize([float(p.review_count) for p in products])

    query_lower = spec.search_query.lower()
    spec_terms = set(query_lower.split())

    for i, p in enumerate(products):
        # Spec match: how many search terms appear in the product title
        title_lower = p.title.lower()
        matched = sum(1 for t in spec_terms if t in title_lower)
        spec_score = matched / max(len(spec_terms), 1)

        avail_score = 1.0 if p.availability == "in_stock" else 0.3

        score = (
            w.get("spec_match", 0.4) * spec_score
            + w.get("rating", 0.2) * ratings[i]
            + w.get("price", 0.2) * prices[i]
            + w.get("availability", 0.1) * avail_score
            + w.get("review_count", 0.1) * reviews[i]
        )
        p.match_score = round(score, 3)

        # Generate reason
        reasons = []
        if spec_score > 0.6:
            reasons.append("Strong spec match")
        if p.rating >= 4.5:
            reasons.append(f"Highly rated ({p.rating}⭐)")
        if prices[i] > 0.7:
            reasons.append("Good price")
        if p.availability == "in_stock":
            reasons.append("In stock")
        p.recommendation_reason = ". ".join(reasons) if reasons else "Relevant result"

    products.sort(key=lambda p: p.match_score, reverse=True)
    for i, p in enumerate(products):
        p.rank = i + 1
    return products
