import json
from pathlib import Path

from langgraph.types import Send

from state import CompetitorProfile
from tools.llm import get_profiler_llm
from tools.scrape import scrape_page
from tools.search import search_tiered
from tools.source_profiles import build_preferred, get_excluded

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "profile.md"
_CHARS_PER_PAGE = 6000
_MAX_PAGES_TO_SCRAPE = 6

# Domains that are the company's own or generic social — deprioritised at scrape time
_LOW_PRIORITY_DOMAINS = {
    "linkedin.com", "instagram.com", "facebook.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com", "reddit.com",
}


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _is_likely_company_owned(url: str, company_name: str) -> bool:
    """Heuristic: True if the URL is probably the company's own site or a social profile."""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower().replace("www.", "")
    if domain in _LOW_PRIORITY_DOMAINS:
        return True
    # Check if the company name (simplified) appears in the domain
    slug = company_name.lower().replace(" ", "").replace(".", "").replace("-", "")
    domain_base = domain.split(".")[0].replace("-", "")
    return slug in domain_base or domain_base in slug


def _gather_research(name: str, geography: str = "") -> tuple[list[str], str]:
    """Run targeted searches covering first-party and third-party sources,
    scrape up to _MAX_PAGES_TO_SCRAPE pages with third-party sources prioritised.

    Returns (source_urls, combined_text).
    """
    preferred = build_preferred("competitive_landscape", geography)
    excluded = get_excluded("competitive_landscape")

    targeted_queries = [
        # First-party: company website + news
        (f"{name} official website about product", 4),
        (f"{name} press release news announcement 2024 2025 2026", 5),
        (f"{name} pricing plans features customers", 4),
        # Third-party: independent reviews + analysis (industry-agnostic wording)
        (f"{name} independent review comparison analysis pros cons", 5),
        (f"{name} customer reviews complaints limitations", 4),
    ]

    # Collect results, deduplicate by URL
    seen_urls: set[str] = set()
    unique_results: list[dict] = []
    for query, n in targeted_queries:
        for r in search_tiered(query, max_results=n,
                               preferred_domains=preferred,
                               excluded_domains=excluded):
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(r)

    # Sort: third-party sources first, company-owned / social last
    unique_results.sort(key=lambda r: _is_likely_company_owned(r.get("url", ""), name))

    # Scrape up to _MAX_PAGES_TO_SCRAPE pages, collect those that return text
    source_urls: list[str] = []
    scraped_sections: list[str] = []
    for r in unique_results[:_MAX_PAGES_TO_SCRAPE]:
        url = r["url"]
        text = scrape_page(url, char_limit=_CHARS_PER_PAGE)
        if text:
            source_urls.append(url)
            scraped_sections.append(f"[Source: {url}]\n{text}")

    import collections
    quality_counts = collections.Counter(r.get("source_quality", "unknown") for r in unique_results)
    print(f"[profile:{name}] source quality: {dict(quality_counts)} — scraping {len(source_urls)} pages")

    if scraped_sections:
        combined_text = "\n\n---\n\n".join(scraped_sections)
    else:
        # All scrapes failed — fall back to Tavily snippets
        combined_text = "\n\n".join(
            f"[Snippet from {r['url']}]\n{r['content']}"
            for r in unique_results
            if r.get("content")
        )[:8000]
        source_urls = [r["url"] for r in unique_results if r.get("url")]

    return source_urls, combined_text


def profile_competitor(state: dict) -> dict:
    """Profile a single competitor. Called via Send fanout — state contains 'name' plus full ResearchState fields."""
    name: str = state["name"]
    geography: str = state.get("geography", "")

    source_urls, combined_text = _gather_research(name, geography)

    industry: str = state.get("industry", "")
    prompt = (
        _load_prompt()
        .replace("{name}", name)
        .replace("{industry}", industry)
        .replace("{text}", combined_text or "No text available.")
    )

    preamble = state.get("scope_preamble", "")
    if preamble:
        prompt = preamble + "\n\n" + prompt

    client, deployment = get_profiler_llm()
    response = client.chat.completions.create(
        model=deployment,
        max_completion_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        extracted = json.loads(raw)
    except json.JSONDecodeError:
        extracted = {"positioning": "Parse error", "icp": "Parse error", "pricing": "Parse error", "differentiator": "Parse error"}

    profile: CompetitorProfile = {
        "name": name,
        "positioning": extracted.get("positioning", "Not specified"),
        "icp": extracted.get("icp", "Not specified"),
        "pricing": extracted.get("pricing", "Not specified"),
        "differentiator": extracted.get("differentiator", "Not specified"),
        "source_urls": source_urls,
    }

    return {"profiles": [profile]}


def fanout(state: dict) -> list[Send]:
    """Conditional edge: fan out one Send per competitor name."""
    return [
        Send("profile_competitor", {**state, "name": name})
        for name in state["competitor_names"]
    ]
