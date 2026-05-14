"""Tavily-backed implementation of the SearchProvider protocol."""
from __future__ import annotations

import os

from tavily import TavilyClient


def raw_search(
    query: str,
    max_results: int = 5,
    topic: str = "general",
    time_range: str | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> list[dict]:
    """Single Tavily search call. No tiering or reranking — that's the caller's job."""
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    kwargs: dict = {"max_results": max_results, "topic": topic}
    if time_range:
        kwargs["time_range"] = time_range
    if include_domains:
        kwargs["include_domains"] = include_domains
    if exclude_domains:
        kwargs["exclude_domains"] = exclude_domains
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
