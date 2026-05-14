import json
import os
from pathlib import Path

from tools.llm import get_discovery_llm
from tools.search import search_tiered
from tools.source_profiles import build_preferred, get_excluded

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "discover.md"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def discover_competitors(state: dict) -> dict:
    industry = state["industry"]
    geography = state["geography"]
    explicit_includes = state.get("explicit_includes", [])
    explicit_excludes = state.get("explicit_excludes", [])

    queries = [
        f"best {industry} tools {geography} 2024 2025",
        f"top {industry} vendors {geography} market leaders",
        f"{industry} Gartner magic quadrant leaders",
        f"{industry} companies {geography} funding series",
        f"{industry} vs comparison alternatives",
    ]
    # Add targeted searches for explicit includes (they may be small/new companies)
    for name in explicit_includes:
        queries.append(f"{name} {industry} {geography}")

    preferred = build_preferred("competitive_landscape", geography)
    excluded = get_excluded("competitive_landscape")
    results = []
    for q in queries:
        results.extend(search_tiered(q, max_results=12,
                                     preferred_domains=preferred,
                                     excluded_domains=excluded))

    search_text = "\n---\n".join(
        f"Title: {r['title']}\nURL: {r['url']}\nSnippet: {r['content']}"
        for r in results
    )

    prompt = _load_prompt().replace("{industry}", industry).replace("{geography}", geography).replace("{search_results}", search_text)

    # Inject include/exclude instructions into the prompt
    scope_instructions = ""
    if explicit_includes:
        scope_instructions += (
            f"\n\n**MUST INCLUDE:** The following companies MUST appear in your output list "
            f"(add them even if they appear in only one search result or none): "
            f"{', '.join(explicit_includes)}\n"
        )
    if explicit_excludes:
        scope_instructions += (
            f"\n**MUST EXCLUDE:** Do NOT include companies that are primarily: "
            f"{', '.join(explicit_excludes)}. "
            f"Use the freed slots to find additional companies that ARE in the "
            f"{industry} space but are NOT in the excluded categories.\n"
        )
    if scope_instructions:
        prompt = prompt + scope_instructions

    preamble = state.get("scope_preamble", "")
    if preamble:
        prompt = preamble + "\n\n" + prompt

    client, deployment = get_discovery_llm()
    response = client.chat.completions.create(
        model=deployment,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    raw = response.choices[0].message.content.strip()
    # Strip markdown code fences if the model adds them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    names: list[str] = json.loads(raw)
    names = [n for n in names if n != "__INSUFFICIENT_DATA__"]
    # Deduplicate preserving order
    seen = set()
    deduped = []
    for n in names:
        key = n.lower().strip()
        if key not in seen:
            seen.add(key)
            deduped.append(n.strip())

    # Ensure explicit includes are in the list (prepend if missing)
    for include in reversed(explicit_includes):
        if include.lower().strip() not in {n.lower().strip() for n in deduped}:
            deduped.insert(0, include)

    # Top 7 get profiled; remainder surface as "also considered" in the report
    competitor_names = deduped[:7]
    also_considered = deduped[7:]

    return {"competitor_names": competitor_names, "also_considered": also_considered}
