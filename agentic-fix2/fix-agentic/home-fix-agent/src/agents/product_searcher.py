"""Product Searcher: query retailer APIs or use mock data."""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
import httpx
from src.models.schemas import ProductResult, ProductSpec
from src.utils.config import _ROOT

logger = logging.getLogger(__name__)

_MOCK_FILE = _ROOT / "data" / "mock_search_results.json"


def _search_serpapi(query: str, api_key: str) -> list[ProductResult]:
    """Search Google Shopping via SerpAPI."""
    results: list[ProductResult] = []
    try:
        resp = httpx.get(
            "https://serpapi.com/search.json",
            params={"engine": "google_shopping", "q": query, "api_key": api_key, "num": 10},
            timeout=30,
        )
        resp.raise_for_status()
        for i, item in enumerate(resp.json().get("shopping_results", [])[:10]):
            price_str = item.get("price", "$0").replace("$", "").replace(",", "")
            try:
                price_cents = int(float(price_str) * 100)
            except ValueError:
                price_cents = 0
            results.append(ProductResult(
                title=item.get("title", ""),
                price_cents=price_cents,
                rating=float(item.get("rating", 0) or 0),
                review_count=int(item.get("reviews", 0) or 0),
                url=item.get("link", ""),
                image_url=item.get("thumbnail", ""),
                asin_or_sku=item.get("product_id", ""),
                rank=i + 1,
            ))
    except Exception as e:
        logger.warning("SerpAPI search failed: %s", e)
    return results


def _search_mock(query: str) -> list[ProductResult]:
    """Return mock search results from fixture file."""
    if not _MOCK_FILE.exists():
        return []
    data = json.loads(_MOCK_FILE.read_text())
    query_lower = query.lower()
    for category, products in data.items():
        if category in query_lower or any(kw in query_lower for kw in category.split("_")):
            return [ProductResult(**p) for p in products]
    # No matching category — return empty rather than unrelated products
    return []


def _search_llm_generated(query: str, item_category: str) -> list[ProductResult]:
    """Use LLM to generate realistic product suggestions when no API or mock match."""
    from src.utils.llm import llm_json

    system = """You are a product search engine. Given a search query, return realistic product results that a user would find on Amazon or Home Depot.

Return JSON: {"products": [{"title": "string", "price_cents": int, "rating": float, "review_count": int, "availability": "in_stock", "url": "", "image_url": "", "asin_or_sku": ""}]}

Rules:
- Return 3-5 products that genuinely match the query
- Use realistic prices, ratings, and review counts
- Include well-known brands for the product category
- price_cents MUST be in cents (e.g., $12.99 = 1299, $3.97 = 397). Do NOT use dollar amounts.
- Leave url and image_url as empty strings — do NOT invent URLs.
- If the item is unusual or not a standard retail product, return fewer results or an empty list"""

    try:
        result = llm_json(system, f"Search query: {query}\nCategory: {item_category}")
        products = []
        for p in result.get("products", []):
            pr = ProductResult(**p)
            # Fix LLM returning dollars instead of cents
            if pr.price_cents > 0 and pr.price_cents < 500:
                pr.price_cents *= 100
            # Add search link if no URL provided
            if not pr.url:
                from urllib.parse import quote_plus
                pr.url = f"https://www.google.com/search?tbm=shop&q={quote_plus(pr.title)}"
            products.append(pr)
        return products
    except Exception as e:
        logger.warning("LLM product search failed: %s", e)
        return []


def search(spec: ProductSpec) -> list[ProductResult]:
    """Search for products. Tries: SerpAPI -> mock fixtures -> LLM-generated."""
    query = spec.search_query
    if not query:
        attrs = " ".join(str(v) for v in spec.attributes.values() if v)
        query = f"{spec.item_category} {attrs}"

    api_key = os.environ.get("SERPAPI_KEY", "")
    if api_key:
        results = _search_serpapi(query, api_key)
        if results:
            return results

    # Try mock data (only returns results for known categories)
    results = _search_mock(query)
    if results:
        logger.info("Using mock results for: %s", query)
        return results

    # Fallback: ask LLM to generate realistic product suggestions
    logger.info("Using LLM-generated results for: %s", query)
    return _search_llm_generated(query, spec.item_category)
