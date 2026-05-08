"""Compiler node — assembles the final report from all section results."""

import re
from datetime import date
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown

from state import ResearchState
from tools.llm import get_writer_llm

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "compiler_executive_summary.md"
_REPORTS_DIR = Path(__file__).parent.parent / "reports"
_console = Console()


def compiler(state: ResearchState) -> dict:
    """Sort sections, generate executive summary, assemble final markdown report."""
    scope = state["scope"]
    industry = scope["industry"]
    geography = scope["geography"]
    preamble = state.get("scope_preamble", "")
    sections = sorted(state["sections"], key=lambda s: s["order"])

    # ── Generate executive summary ──────────────────────────────────────────
    section_markdowns = "\n\n---\n\n".join(
        f"## {s['title']}\n\n{s['markdown']}" for s in sections
    )

    prompt = (
        _PROMPT_PATH.read_text(encoding="utf-8")
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
    all_sources: list[str] = []
    for section in sections:
        for url in section.get("sources", []):
            if url not in seen:
                seen.add(url)
                all_sources.append(url)

    sources_md = "\n".join(f"- {url}" for url in all_sources)

    # ── Assemble final report ───────────────────────────────────────────────
    iso_date = date.today().isoformat()

    # Section header emoji mapping for visual scanning
    _SECTION_EMOJI = {
        "Competitive Landscape": "🔬",
        "Market Trends": "📈",
        "Investment & Funding Activity": "💰",
    }

    section_bodies = "\n\n---\n\n".join(
        f"## {_SECTION_EMOJI.get(s['title'], '📋')} {s['title']}\n\n{s['markdown']}"
        for s in sections
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
