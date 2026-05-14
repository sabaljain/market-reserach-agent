"""Search facade with three-pass tiered retrieval over a pluggable provider.

The active backend is chosen by the SEARCH_PROVIDER env var:
    "tavily"   (default) — uses Tavily AI search API
    "openserp" — uses a self-hosted OpenSERP container (see docker-compose.openserp.yml)

Switching providers does not require call-site changes; `search_tiered` keeps
the same signature and result shape.
"""
from __future__ import annotations

import os
from typing import Callable

try:
    from langsmith import traceable
except ImportError:
    def traceable(**_kw):  # type: ignore[misc]
        return lambda f: f

_FALLBACK_THRESHOLD = 6

# Provider type: callable matching the raw_search signature.
ProviderFn = Callable[..., list[dict]]


def get_provider() -> ProviderFn:
    """Return the active search provider's raw_search function."""
    name = os.environ.get("SEARCH_PROVIDER", "openserp").lower().strip()
    if name == "openserp":
        from tools.providers import openserp_provider
        return openserp_provider.raw_search
    if name == "tavily":
        from tools.providers import tavily_provider
        return tavily_provider.raw_search
    raise ValueError(f"Unknown SEARCH_PROVIDER: {name!r} (expected 'tavily' or 'openserp')")


def search(
    query: str,
    max_results: int = 5,
    topic: str = "general",
    time_range: str | None = None,
) -> list[dict]:
    """Run a single search and return a list of result dicts.

    Extra keys (score, published_date) are populated when available and used
    by the Trends agent for ranking; existing callers safely ignore them.
    """
    return get_provider()(
        query,
        max_results=max_results,
        topic=topic,
        time_range=time_range,
    )


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
    After all passes, results are reranked locally to recover relevance ordering
    when the underlying provider doesn't supply a strong score signal.
    """
    provider = get_provider()
    seen_urls: set[str] = set()
    results: list[dict] = []

    def _run_pass(include: list[str] | None, exclude: list[str] | None, quality: str) -> list[dict]:
        raw = provider(
            query,
            max_results=max_results,
            topic=topic,
            time_range=time_range,
            include_domains=include,
            exclude_domains=exclude,
        )
        out = []
        for r in raw:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                out.append({**r, "source_quality": quality})
        return out

    # Pass 1 — preferred sources
    results.extend(_run_pass(preferred_domains or None, excluded_domains, "preferred"))

    # Pass 2 — general sources (fallback)
    if len(results) < _FALLBACK_THRESHOLD:
        results.extend(_run_pass(None, excluded_domains, "general"))

    # Pass 3 — low-quality last resort
    if len(results) < _FALLBACK_THRESHOLD:
        results.extend(_run_pass(None, None, "low"))

    # Local rerank to recover ranking quality (esp. for providers without a native score).
    try:
        from tools.rerank import rerank
        results = rerank(query, results, preferred_domains=preferred_domains or [])
    except ImportError:
        # rerank module optional during partial rollouts
        pass

    return results
