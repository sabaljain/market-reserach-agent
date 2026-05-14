"""Compiler node — composes findings into section markdown, then assembles the final report."""

import json
import logging
import re
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown

from state import ResearchState
from tools.llm import get_writer_llm

logger = logging.getLogger(__name__)

_EXEC_SUMMARY_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "compiler_executive_summary.md"
_REPORTS_DIR = Path(__file__).parent.parent / "reports"
_console = Console()

_COMPOSE_PROMPTS: dict[str, Path] = {
    "competitive_landscape": Path(__file__).parent.parent / "prompts" / "compose_competitive_landscape.md",
    "trends": Path(__file__).parent.parent / "prompts" / "compose_trends.md",
    "investment": Path(__file__).parent.parent / "prompts" / "compose_investment.md",
}


def _compose_section(section: dict, industry: str, geography: str, preamble: str) -> str:
    """Turn a SectionFindings object into section markdown via LLM composition."""
    section_id = section["section_id"]
    findings = section.get("findings", [])

    prompt_path = _COMPOSE_PROMPTS.get(section_id)
    if not prompt_path or not prompt_path.exists():
        logger.warning("[compiler] no composition prompt for section_id=%r; using raw findings", section_id)
        return "\n\n".join(
            f"**{f.get('headline', 'Untitled')}**\n\n{f.get('evidence_summary', '')}"
            for f in findings
        )

    prompt = (
        prompt_path.read_text(encoding="utf-8")
        .replace("{industry}", industry)
        .replace("{geography}", geography)
        .replace("{findings_json}", json.dumps(findings, indent=2))
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


def compiler(state: ResearchState) -> dict:
    """Compose findings into section markdown, generate executive summary, assemble final report."""
    scope = state["scope"]
    industry = scope["industry"]
    geography = scope["geography"]
    preamble = state.get("scope_preamble", "")
    sections = sorted(state["sections"], key=lambda s: s["order"])

    # ── Compose each section's findings into markdown ───────────────────────
    composed_sections: list[dict] = []
    for section in sections:
        if "findings" in section:
            markdown = _compose_section(section, industry, geography, preamble)
            logger.info(
                "[compiler] composed %s: %d findings → %d chars markdown",
                section["section_id"], len(section.get("findings", [])), len(markdown),
            )
        else:
            # Backward compatibility: if a section already has markdown (e.g., fallback)
            markdown = section.get("markdown", "")
        composed_sections.append({
            "title": section["title"],
            "order": section["order"],
            "markdown": markdown,
            "sources": section.get("sources", []),
        })

    # ── Generate executive summary ──────────────────────────────────────────
    section_markdowns = "\n\n---\n\n".join(
        f"## {s['title']}\n\n{s['markdown']}" for s in composed_sections
    )

    prompt = (
        _EXEC_SUMMARY_PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{industry}", industry)
        .replace("{geography}", geography)
        .replace("{section_markdowns}", section_markdowns)
    )
    if preamble:
        prompt = preamble + "\n\n" + prompt

    client, deployment = get_writer_llm()
    response = client.chat.completions.create(
        model=deployment,
        max_completion_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    exec_summary = response.choices[0].message.content.strip()

    # ── Deduplicate all sources ─────────────────────────────────────────────
    seen: set[str] = set()
    all_source_urls: list[str] = []
    for section in composed_sections:
        for source in section.get("sources", []):
            # Handle both Source dicts and plain URL strings
            url = source["url"] if isinstance(source, dict) else source
            if url and url not in seen:
                seen.add(url)
                all_source_urls.append(url)

    sources_md = "\n".join(f"- {url}" for url in all_source_urls)

    # ── Assemble final report ───────────────────────────────────────────────
    iso_date = date.today().isoformat()

    _SECTION_EMOJI = {
        "Competitive Landscape": "🔬",
        "Market Trends": "📈",
        "Investment & Funding Activity": "💰",
    }

    section_bodies = "\n\n---\n\n".join(
        f"## {_SECTION_EMOJI.get(s['title'], '📋')} {s['title']}\n\n{s['markdown']}"
        for s in composed_sections
    )

    final_report = f"""# 🌐 Market Research: {industry} — {geography}
_Generated {iso_date}_

---

## 🎯 Executive Summary

{exec_summary}

---

{section_bodies}

---

## 📚 Sources

{sources_md}
"""

    # ── Print to terminal ───────────────────────────────────────────────────
    _console.print(Markdown(final_report))

    # ── Save to reports/ ────────────────────────────────────────────────────
    _REPORTS_DIR.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9]", "_", industry)[:30]
    ts = date.today().strftime("%Y%m%d")
    filepath = _REPORTS_DIR / f"{ts}_{slug}.md"
    filepath.write_text(final_report, encoding="utf-8")

    return {"final_report": final_report}
