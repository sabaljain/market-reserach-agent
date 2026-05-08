"""Investment & Funding Activity section agent.

Five-step sequential pipeline:
  1. generate_investment_queries — LLM produces targeted news-search queries
  2. fetch_news                  — Tavily news search, dedup, rank by score
  3. scrape_top_sources          — fetch full text for highest-relevance items
  4. extract_evidence            — LLM extracts typed deal evidence items
  5. write_investment_section    — LLM writes section markdown from evidence list
"""

import collections
import json
from pathlib import Path

from nodes.sections.base import make_section_result
from tools.llm import get_discovery_llm, get_writer_llm
from tools.scrape import scrape_page
from tools.search import search_tiered
from tools.source_profiles import build_preferred, get_excluded

_QUERY_PROMPT_PATH     = Path(__file__).parent.parent.parent / "prompts" / "investment_query_generator.md"
_EXTRACTOR_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "investment_evidence_extractor.md"
_WRITER_PROMPT_PATH    = Path(__file__).parent.parent.parent / "prompts" / "investment_writer.md"

_MAX_NEWS_ITEMS = 25
_SCRAPE_TOP_N = 8
_CHARS_PER_PAGE = 6000


# ── Step 1 ───────────────────────────────────────────────────────────────────

def _generate_investment_queries(scope: dict, preamble: str = "") -> list[str]:
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
    preferred = build_preferred("investment", scope.get("geography", ""))
    excluded = get_excluded("investment")
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

def _scrape_top_sources(news_items: list[dict], top_n: int = _SCRAPE_TOP_N) -> list[dict]:
    enriched: list[dict] = []
    for item in news_items[:top_n]:
        url = item.get("url", "")
        full_text = scrape_page(url, char_limit=_CHARS_PER_PAGE) if url else ""
        enriched.append({**item, "full_text": full_text or item.get("content", "")})
    for item in news_items[top_n:]:
        enriched.append({**item, "full_text": item.get("content", "")})
    return enriched


# ── Step 4 ───────────────────────────────────────────────────────────────────

def _extract_evidence(enriched: list[dict], scope: dict, preamble: str = "") -> list[dict]:
    """Extract typed deal evidence items from all scraped sources."""
    scraped_items = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "published_date": r.get("published_date", ""),
            "full_text": r.get("full_text", ""),
            "source_quality": r.get("source_quality", "general"),
        }
        for r in enriched
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


# ── Step 5 ───────────────────────────────────────────────────────────────────

def _write_investment_section(evidence: list[dict], scope: dict, preamble: str = "") -> str:
    prompt = (
        _WRITER_PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{industry}", scope["industry"])
        .replace("{geography}", scope["geography"])
        .replace("{additional_context}", scope.get("additional_context", ""))
        .replace("{evidence_json}", json.dumps(evidence, indent=2))
    )
    if preamble:
        prompt = preamble + "\n\n" + prompt

    client, deployment = get_writer_llm()
    response = client.chat.completions.create(
        model=deployment,
        max_completion_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.choices[0].message.content.strip()


# ── Public entry point ────────────────────────────────────────────────────────

def run(section_spec: dict, scope: dict, scope_preamble: str = "") -> dict:
    queries  = _generate_investment_queries(scope, scope_preamble)
    news     = _fetch_news(queries, scope)
    enriched = _scrape_top_sources(news, top_n=_SCRAPE_TOP_N)
    evidence = _extract_evidence(enriched, scope, scope_preamble)
    markdown = _write_investment_section(evidence, scope, scope_preamble)

    quality_counts = collections.Counter(r.get("source_quality", "unknown") for r in enriched)
    fact_count = sum(1 for e in evidence if e.get("claim_type") == "fact")
    print(
        f"[investment] evidence: {len(evidence)} items ({fact_count} facts) | "
        f"source quality: {dict(quality_counts)}"
    )

    sources = list(dict.fromkeys(item["url"] for item in enriched if item.get("url")))

    return {
        "sections": [
            make_section_result(
                section_id=section_spec["section_id"],
                title=section_spec.get("title", "Investment & Funding Activity"),
                order=section_spec["order"],
                markdown=markdown,
                sources=sources,
            )
        ]
    }
