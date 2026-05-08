import os

from tavily import TavilyClient

try:
    from langsmith import traceable
except ImportError:
    def traceable(**_kw):  # type: ignore[misc]
        return lambda f: f

_FALLBACK_THRESHOLD = 3


def search(
    query: str,
    max_results: int = 5,
    topic: str = "general",
    time_range: str | None = None,
) -> list[dict]:
    """Run a Tavily search and return a list of result dicts.

    Extra keys (score, published_date) are populated when available and used
    by the Trends agent for ranking; existing callers safely ignore them.
    """
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    kwargs: dict = {"max_results": max_results, "topic": topic}
    if time_range:
        kwargs["time_range"] = time_range
    response = client.search(query, **kwargs)
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
            "score": r.get("score", 0.0),
            "published_date": r.get("published_date", ""),
        }
        for r in response.get("results", [])
    ]


@traceable(name="search_tiered", run_type="tool")
def search_tiered(
    query: str,
    max_results: int = 5,
    topic: str = "general",
    time_range: str | None = None,
    preferred_domains: list[str] | None = None,
    excluded_domains: list[str] | None = None,
) -> list[dict]:
    """Three-pass domain-biased search with source_quality tag on every result.

    Pass 1: include preferred_domains + exclude excluded_domains  → tag "preferred"
    Pass 2: drop include, keep exclude (if pass 1 < threshold)   → tag "general"
    Pass 3: drop both (if pass 2 still insufficient)             → tag "low"

    Results are deduplicated by URL across passes. Earlier-pass quality wins.
    """
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    seen_urls: set[str] = set()
    results: list[dict] = []

    def _run_pass(include: list[str] | None, exclude: list[str] | None, quality: str) -> list[dict]:
        kwargs: dict = {"max_results": max_results, "topic": topic}
        if time_range:
            kwargs["time_range"] = time_range
        if include:
            kwargs["include_domains"] = include
        if exclude:
            kwargs["exclude_domains"] = exclude
        response = client.search(query, **kwargs)
        out = []
        for r in response.get("results", []):
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                out.append({
                    "title": r.get("title", ""),
                    "url": url,
                    "content": r.get("content", ""),
                    "score": r.get("score", 0.0),
                    "published_date": r.get("published_date", ""),
                    "source_quality": quality,
                })
        return out

    # Pass 1 — preferred sources
    results.extend(_run_pass(preferred_domains or None, excluded_domains, "preferred"))

    # Pass 2 — general sources (fallback)
    if len(results) < _FALLBACK_THRESHOLD:
        results.extend(_run_pass(None, excluded_domains, "general"))

    # Pass 3 — low-quality last resort
    if len(results) < _FALLBACK_THRESHOLD:
        results.extend(_run_pass(None, None, "low"))

    return results
