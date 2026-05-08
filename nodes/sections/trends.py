"""Trends section agent.

Seven-step sequential pipeline:
  1. generate_trend_queries   — LLM produces targeted news-search queries
  2. fetch_news               — Tavily news search, dedup, rank by score
  3. fetch_market_context     — 2 general-web searches for market sizing/growth data
  4. scrape_top_sources       — fetch full text for highest-relevance items
  5. extract_evidence         — LLM extracts typed evidence items from scraped text
  6. detect_themes            — LLM groups evidence into qualified trends + weak signals
  7. write_trends_section     — LLM writes section markdown from evidence + themes
"""

import collections
import json
from pathlib import Path

from nodes.sections.base import make_section_result
from tools.llm import get_discovery_llm, get_writer_llm
from tools.scrape import scrape_page
from tools.search import search_tiered
from tools.source_profiles import build_preferred, get_excluded

_QUERY_PROMPT_PATH     = Path(__file__).parent.parent.parent / "prompts" / "trends_query_generator.md"
_EXTRACTOR_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "trends_evidence_extractor.md"
_THEME_PROMPT_PATH     = Path(__file__).parent.parent.parent / "prompts" / "trends_theme_detector.md"
_WRITER_PROMPT_PATH    = Path(__file__).parent.parent.parent / "prompts" / "trends_writer.md"

_MAX_NEWS_ITEMS = 25
_SCRAPE_TOP_N = 8
_CHARS_PER_PAGE = 6000


# ── Step 1 ───────────────────────────────────────────────────────────────────

def _generate_trend_queries(scope: dict, preamble: str = "") -> list[str]:
    prompt = (
        _QUERY_PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{industry}", scope["industry"])
        .replace("{geography}", scope["geography"])
        .replace("{additional_context}", scope.get("additional_context", ""))
    )
    if preamble:
        prompt = preamble + "\n\n" + prompt

    client, deployment = get_discovery_llm()
    response = client.chat.completions.create(
        model=deployment,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    queries: list[str] = json.loads(raw)
    return [q for q in queries if q != "__INSUFFICIENT_DATA__"]


# ── Step 2 ───────────────────────────────────────────────────────────────────

def _fetch_news(queries: list[str], scope: dict) -> list[dict]:
    preferred = build_preferred("trends", scope.get("geography", ""))
    excluded = get_excluded("trends")
    seen_urls: set[str] = set()
    items: list[dict] = []

    for query in queries:
        for r in search_tiered(query, max_results=8, topic="news", time_range="year",
                               preferred_domains=preferred, excluded_domains=excluded):
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                items.append({**r, "source_query": query})

    items.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return items[:_MAX_NEWS_ITEMS]


# ── Step 3 ───────────────────────────────────────────────────────────────────

def _fetch_market_context(scope: dict) -> list[dict]:
    """Run 2 general-web searches for market sizing, growth rates, and structural data."""
    industry = scope["industry"]
    geography = scope["geography"]
    preferred = build_preferred("trends", geography)
    excluded = get_excluded("trends")
    context_queries = [
        f'"{industry}" market size CAGR growth rate forecast {geography} 2024 2025',
        f'"{industry}" adoption penetration fastest growing segment {geography} 2025',
    ]
    seen_urls: set[str] = set()
    items: list[dict] = []
    for query in context_queries:
        for r in search_tiered(query, max_results=5, topic="general",
                               preferred_domains=preferred, excluded_domains=excluded):
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                items.append({**r, "source_query": query})
    return items


# ── Step 4 ───────────────────────────────────────────────────────────────────

def _scrape_top_sources(news_items: list[dict], top_n: int = _SCRAPE_TOP_N) -> list[dict]:
    enriched: list[dict] = []
    for item in news_items[:top_n]:
        url = item.get("url", "")
        full_text = scrape_page(url, char_limit=_CHARS_PER_PAGE) if url else ""
        enriched.append({**item, "full_text": full_text or item.get("content", "")})
    for item in news_items[top_n:]:
        enriched.append({**item, "full_text": item.get("content", "")})
    return enriched


# ── Step 5 ───────────────────────────────────────────────────────────────────

def _extract_evidence(enriched: list[dict], market_context_enriched: list[dict],
                      scope: dict, preamble: str = "") -> list[dict]:
    """Extract typed evidence items from all scraped sources."""
    scraped_items = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "published_date": r.get("published_date", ""),
            "full_text": r.get("full_text", ""),
            "source_quality": r.get("source_quality", "general"),
        }
        for r in enriched + market_context_enriched
    ]

    prompt = (
        _EXTRACTOR_PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{industry}", scope["industry"])
        .replace("{geography}", scope["geography"])
        .replace("{scraped_items_json}", json.dumps(scraped_items, indent=2))
    )
    if preamble:
        prompt = preamble + "\n\n" + prompt

    client, deployment = get_discovery_llm()
    response = client.chat.completions.create(
        model=deployment,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_completion_tokens=4096,
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


# ── Step 6 ───────────────────────────────────────────────────────────────────

def _detect_themes(evidence: list[dict], scope: dict) -> dict:
    """Group evidence into qualified trends and weak signals."""
    prompt = (
        _THEME_PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{industry}", scope["industry"])
        .replace("{geography}", scope["geography"])
        .replace("{evidence_json}", json.dumps(evidence, indent=2))
    )

    client, deployment = get_discovery_llm()
    response = client.chat.completions.create(
        model=deployment,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_completion_tokens=2048,
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"qualified_trends": [], "weak_signals": []}


# ── Step 7 ───────────────────────────────────────────────────────────────────

def _write_trends_section(evidence: list[dict], themes: dict,
                          scope: dict, preamble: str = "") -> str:
    prompt = (
        _WRITER_PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{industry}", scope["industry"])
        .replace("{geography}", scope["geography"])
        .replace("{additional_context}", scope.get("additional_context", ""))
        .replace("{evidence_json}", json.dumps(evidence, indent=2))
        .replace("{theme_groups_json}", json.dumps(themes, indent=2))
    )
    if preamble:
        prompt = preamble + "\n\n" + prompt

    client, deployment = get_writer_llm()
    response = client.chat.completions.create(
        model=deployment,
        max_completion_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.choices[0].message.content.strip()


# ── Public entry point ────────────────────────────────────────────────────────

def run(section_spec: dict, scope: dict, scope_preamble: str = "") -> dict:
    queries             = _generate_trend_queries(scope, scope_preamble)
    news                = _fetch_news(queries, scope)
    market_context      = _fetch_market_context(scope)
    enriched            = _scrape_top_sources(news, top_n=_SCRAPE_TOP_N)
    market_context_enr  = _scrape_top_sources(market_context, top_n=3)
    evidence            = _extract_evidence(enriched, market_context_enr, scope, scope_preamble)
    themes              = _detect_themes(evidence, scope)
    markdown            = _write_trends_section(evidence, themes, scope, scope_preamble)

    quality_counts = collections.Counter(r.get("source_quality", "unknown") for r in enriched + market_context_enr)
    print(
        f"[trends] evidence: {len(evidence)} items | "
        f"qualified trends: {len(themes.get('qualified_trends', []))} | "
        f"weak signals: {len(themes.get('weak_signals', []))} | "
        f"source quality: {dict(quality_counts)}"
    )

    sources = list(dict.fromkeys(item["url"] for item in enriched if item.get("url")))

    return {
        "sections": [
            make_section_result(
                section_id=section_spec["section_id"],
                title=section_spec.get("title", "Market Trends"),
                order=section_spec["order"],
                markdown=markdown,
                sources=sources,
            )
        ]
    }
