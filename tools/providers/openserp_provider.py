"""OpenSERP-backed implementation of the SearchProvider protocol.

OpenSERP is a self-hosted SERP scraper (https://github.com/karust/openserp).
We hit its `/mega/search` endpoint which aggregates results across multiple
engines (google, bing, duckduckgo, yandex, ...) with native dedup.

Map from our canonical params:
    include_domains   -> appended as `site:(a.com OR b.com)` query operator
    exclude_domains   -> appended as ` -site:a.com -site:b.com`
    time_range        -> converted to `date=YYYYMMDD..YYYYMMDD`
    topic="news"      -> restrict engines to google,bing,duckduckgo +
                         append "news" keyword bias (OpenSERP has no topic param)

Response fields without a reliable equivalent are returned empty:
    score=0.0          (filled in later by tools.rerank)
    published_date=""  (engine-dependent, mostly absent)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import requests

_DEFAULT_BASE_URL = "http://localhost:7000"
_HTTP_TIMEOUT_SECONDS = 30


def _time_range_to_date(time_range: str | None) -> str | None:
    """Convert 'day'|'week'|'month'|'year' to OpenSERP `date=YYYYMMDD..YYYYMMDD`."""
    if not time_range:
        return None
    days_by_range = {"day": 1, "week": 7, "month": 30, "year": 365}
    days = days_by_range.get(time_range.lower())
    if days is None:
        return None
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    return f"{start.strftime('%Y%m%d')}..{end.strftime('%Y%m%d')}"


def _build_query(query: str, include_domains: list[str] | None, exclude_domains: list[str] | None,
                 topic: str) -> str:
    """Augment the query string with site:/-site:/news operators."""
    parts: list[str] = [query]
    if include_domains:
        sites = " OR ".join(f"site:{d}" for d in include_domains)
        parts.append(f"({sites})")
    if exclude_domains:
        for d in exclude_domains:
            parts.append(f"-site:{d}")
    if topic and topic.lower() == "news":
        parts.append("news")
    return " ".join(parts)


def raw_search(
    query: str,
    max_results: int = 5,
    topic: str = "general",
    time_range: str | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> list[dict]:
    """Single OpenSERP megasearch call. No tiering — that's the caller's job."""
    base_url = os.environ.get("OPENSERP_URL", _DEFAULT_BASE_URL).rstrip("/")
    augmented_query = _build_query(query, include_domains, exclude_domains, topic)

    params: dict = {
        "text": augmented_query,
        "limit": max_results,
        "mode": "balanced",
        "dedupe": "true",
        "merge": "true",
    }
    if topic and topic.lower() == "news":
        params["engines"] = "google,bing,duckduckgo"

    date_range = _time_range_to_date(time_range)
    if date_range:
        params["date"] = date_range

    try:
        response = requests.get(f"{base_url}/mega/search", params=params, timeout=_HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException:
        return []

    payload = response.json() if response.content else {}
    raw_results = payload.get("results", []) or []

    out: list[dict] = []
    for r in raw_results:
        url = r.get("url", "")
        if not url:
            continue
        out.append({
            "title": r.get("title", ""),
            "url": url,
            "content": r.get("snippet", ""),
            "score": 0.0,
            "published_date": r.get("published_date", "") or "",
        })
    return out
