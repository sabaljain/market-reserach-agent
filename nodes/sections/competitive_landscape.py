"""Competitive Landscape section agent.

Internally runs a LangGraph sub-graph that replicates v1's
Discovery → Profiler (fanout) → Section Writer pipeline.
"""

import json
import operator
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from nodes.discover import discover_competitors as _v1_discover
from nodes.profile import profile_competitor as _v1_profile
from nodes.sections.base import make_section_result
from state import CompetitorProfile
from tools.llm import get_writer_llm

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "competitive_landscape_writer.md"


# ── Internal sub-graph state ────────────────────────────────────────────────

class _CLState(TypedDict):
    industry: str
    geography: str
    scope_preamble: str
    explicit_includes: list[str]
    explicit_excludes: list[str]
    competitor_names: list[str]
    also_considered: list[str]
    profiles: Annotated[list[CompetitorProfile], operator.add]
    section_markdown: str


# ── Internal nodes ──────────────────────────────────────────────────────────

def _discover(state: _CLState) -> dict:
    """Wraps v1 discover_competitors — adapts state shape."""
    # v1 discover expects a dict with 'industry' and 'geography' keys
    result = _v1_discover(state)
    return {
        "competitor_names": result["competitor_names"],
        "also_considered": result.get("also_considered", []),
    }


def _profile(state: dict) -> dict:
    """Wraps v1 profile_competitor — called via Send fanout."""
    return _v1_profile(state)


def _fanout(state: _CLState) -> list[Send]:
    """Emit one Send per competitor name for parallel profiling."""
    return [
        Send("_profile", {**state, "name": name})
        for name in state["competitor_names"]
    ]


def _write_section(state: _CLState) -> dict:
    """LLM call to produce the section markdown from profiles."""
    profiles_json = json.dumps(state["profiles"], indent=2)
    also_considered = state.get("also_considered", [])
    also_considered_text = ", ".join(also_considered) if also_considered else "None"
    preamble = state.get("scope_preamble", "")

    prompt = (
        _PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{industry}", state["industry"])
        .replace("{geography}", state["geography"])
        .replace("{profiles_json}", profiles_json)
        .replace("{also_considered}", also_considered_text)
    )
    if preamble:
        prompt = preamble + "\n\n" + prompt

    client, deployment = get_writer_llm()
    response = client.chat.completions.create(
        model=deployment,
        max_completion_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    markdown = response.choices[0].message.content.strip()
    return {"section_markdown": markdown}


# ── Build the sub-graph (compiled once at module load) ──────────────────────

def _build_subgraph():
    builder = StateGraph(_CLState)
    builder.add_node("_discover", _discover)
    builder.add_node("_profile", _profile)
    builder.add_node("_write_section", _write_section)

    builder.add_edge(START, "_discover")
    builder.add_conditional_edges("_discover", _fanout)
    builder.add_edge("_profile", "_write_section")
    builder.add_edge("_write_section", END)

    return builder.compile()


_subgraph = _build_subgraph()


# ── Public entry point (called by section_router) ───────────────────────────

def run(section_spec: dict, scope: dict, scope_preamble: str = "") -> dict:
    """Run the competitive landscape sub-graph and return section result."""
    result = _subgraph.invoke(
        {
            "industry": scope["industry"],
            "geography": scope["geography"],
            "scope_preamble": scope_preamble,
            "explicit_includes": scope.get("explicit_includes", []),
            "explicit_excludes": scope.get("explicit_excludes", []),
            "competitor_names": [],
            "also_considered": [],
            "profiles": [],
            "section_markdown": "",
        }
    )

    # Collect all source URLs from profiles
    all_sources: list[str] = []
    for profile in result.get("profiles", []):
        all_sources.extend(profile.get("source_urls", []))
    # Deduplicate preserving order
    seen: set[str] = set()
    unique_sources: list[str] = []
    for url in all_sources:
        if url not in seen:
            seen.add(url)
            unique_sources.append(url)

    section_result = make_section_result(
        section_id=section_spec["section_id"],
        title=section_spec["title"],
        order=section_spec["order"],
        markdown=result["section_markdown"],
        sources=unique_sources,
    )

    return {"sections": [section_result]}
