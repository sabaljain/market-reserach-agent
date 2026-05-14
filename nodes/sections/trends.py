"""Trends section agent.

Seven-step sequential pipeline:
  1. generate_trend_queries   — LLM produces targeted news-search queries
  2. fetch_news               — Tavily news search, dedup, rank by score
  3. fetch_market_context     — 2 general-web searches for market sizing/growth data
  4. scrape_top_sources       — fetch full text for highest-relevance items
  5. extract_evidence         — LLM extracts typed evidence items from scraped text
  6. detect_themes            — LLM groups evidence into qualified trends + weak signals
  7. generate_findings        — LLM produces structured Finding objects from evidence + themes
"""

import collections
import json
import logging
from pathlib import Path

from nodes.sections.base import make_section_findings, make_source
from tools.llm import get_discovery_llm, get_writer_llm
from tools.scrape import scrape_page
from tools.search import search_tiered
from tools.source_profiles import build_preferred, get_excluded

logger = logging.getLogger(__name__)

_QUERY_PROMPT_PATH     = Path(__file__).parent.parent.parent / "prompts" / "trends_query_generator.md"
_EXTRACTOR_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "trends_evidence_extractor.md"
_THEME_PROMPT_PATH     = Path(__file__).parent.parent.parent / "prompts" / "trends_theme_detector.md"
_WRITER_PROMPT_PATH    = Path(__file__).parent.parent.parent / "prompts" / "trends_writer.md"
_FINDINGS_PROMPT_PATH  = Path(__file__).parent.parent.parent / "prompts" / "trends_findings_generator.md"

_MAX_NEWS_ITEMS = 25
_SCRAPE_TOP_N = 8
_CHARS_PER_PAGE = 6000


# ── Step 1 ───────────────────────────────────────────────────────────────────

def _generate_trend_queries(section_spec: dict, scope: dict, preamble: str = "") -> list[str]:
    prompt = (
        _QUERY_PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{industry}", scope["industry"])
        .replace("{geography}", scope["geography"])
        .replace("{additional_context}", scope.get("additional_context", ""))
    )
    if preamble:
        prompt = preamble + "\n\n" + prompt

    research_questions = section_spec.get("research_questions", [])
    suggested_queries = section_spec.get("suggested_queries", [])
    if research_questions:
        prompt += "\n\n## Research Questions to Address\nYour queries must surface evidence to answer these specific questions:\n" + "\n".join(f"- {q}" for q in research_questions)
    if suggested_queries:
        prompt += "\n\n## Suggested Starting Queries\nStart with or adapt these queries:\n" + "\n".join(f"- {q}" for q in suggested_queries)

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
        for r in search_tiered(query, max_results=15, topic="news", time_range="year",
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
        for r in search_tiered(query, max_results=10, topic="general",
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

def _extract_evidence(section_spec: dict, enriched: list[dict], market_context_enriched: list[dict],
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

    research_questions = section_spec.get("research_questions", [])
    if research_questions:
        prompt += "\n\n## Target Questions\nExtract evidence that helps answer:\n" + "\n".join(f"- {q}" for q in research_questions)

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

def _generate_findings(section_spec: dict, evidence: list[dict], themes: dict,
                       scope: dict, preamble: str = "") -> tuple[list[dict], str]:
    """Produce structured Finding objects from evidence + themes."""
    prompt = (
        _FINDINGS_PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{industry}", scope["industry"])
        .replace("{geography}", scope["geography"])
        .replace("{additional_context}", scope.get("additional_context", ""))
        .replace("{evidence_json}", json.dumps(evidence, indent=2))
        .replace("{theme_groups_json}", json.dumps(themes, indent=2))
    )
    if preamble:
        prompt = preamble + "\n\n" + prompt

    output_focus = section_spec.get("output_focus", "")
    research_questions = section_spec.get("research_questions", [])
    if output_focus:
        prompt += f"\n\n## Output Focus\nPrioritize: {output_focus}"
    if research_questions:
        prompt += "\n\n## Questions This Section Must Answer\n" + "\n".join(f"- {q}" for q in research_questions)

    client, deployment = get_writer_llm()
    response = client.chat.completions.create(
        model=deployment,
        max_completion_tokens=4096,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )

    raw = json.loads(response.choices[0].message.content)
    findings = raw.get("findings", [])
    for f in findings:
        f.setdefault("evidence_ids", [])
        f.setdefault("confidence", "moderate")
        f.setdefault("relevant_to_other_sections", [])
    return findings, raw.get("sufficiency_self_assessment", "")


# ── Public entry point ────────────────────────────────────────────────────────

def run(section_spec: dict, scope: dict, scope_preamble: str = "") -> dict:
    queries             = _generate_trend_queries(section_spec, scope, scope_preamble)
    news                = _fetch_news(queries, scope)
    market_context      = _fetch_market_context(scope)
    enriched            = _scrape_top_sources(news, top_n=_SCRAPE_TOP_N)
    market_context_enr  = _scrape_top_sources(market_context, top_n=3)
    evidence            = _extract_evidence(section_spec, enriched, market_context_enr, scope, scope_preamble)

    min_threshold = section_spec.get("minimum_evidence_threshold", 8)
    if len(evidence) < min_threshold:
        logger.warning("[trends] evidence %d below threshold %d", len(evidence), min_threshold)

    themes              = _detect_themes(evidence, scope)
    findings, self_assessment = _generate_findings(section_spec, evidence, themes, scope, scope_preamble)

    quality_counts = collections.Counter(r.get("source_quality", "unknown") for r in enriched + market_context_enr)
    print(
        f"[trends] findings: {len(findings)} | "
        f"qualified trends: {len(themes.get('qualified_trends', []))} | "
        f"weak signals: {len(themes.get('weak_signals', []))} | "
        f"source quality: {dict(quality_counts)}"
    )

    section_id = section_spec["section_id"]
    seen_urls: set[str] = set()
    sources = []
    for item in enriched + market_context_enr:
        url = item.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            sources.append(make_source(
                url=url,
                title=item.get("title", ""),
                section_id=section_id,
                quality_tier=item.get("source_quality", "general"),
            ))

    return {
        "sections": [
            make_section_findings(
                section_id=section_id,
                title=section_spec.get("title", "Market Trends"),
                order=section_spec["order"],
                findings=findings,
                sources=sources,
                sufficiency_self_assessment=self_assessment,
            )
        ]
    }
