"""Competitive Landscape section agent.

Internally runs a LangGraph sub-graph that replicates v1's
Discovery → Profiler (fanout) → Findings Generator pipeline.
"""

import json
import logging
import operator
from pathlib import Path
from typing import Annotated, TypedDict

logger = logging.getLogger(__name__)

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from nodes.discover import discover_competitors as _v1_discover
from nodes.profile import profile_competitor as _v1_profile
from nodes.sections.base import make_section_findings, make_source
from state import CompetitorProfile
from tools.llm import get_writer_llm

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "competitive_landscape_writer.md"
_FINDINGS_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "competitive_landscape_findings_generator.md"


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
    research_questions: list[str]
    suggested_queries: list[str]
    output_focus: str
    minimum_evidence_threshold: int
    findings: list[dict]
    sufficiency_self_assessment: str


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


def _generate_findings(state: _CLState) -> dict:
    """LLM call to produce structured findings from profiles."""
    profiles_json = json.dumps(state["profiles"], indent=2)
    also_considered = state.get("also_considered", [])
    also_considered_text = ", ".join(also_considered) if also_considered else "None"
    preamble = state.get("scope_preamble", "")

    prompt = (
        _FINDINGS_PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{industry}", state["industry"])
        .replace("{geography}", state["geography"])
        .replace("{profiles_json}", profiles_json)
        .replace("{also_considered}", also_considered_text)
    )
    if preamble:
        prompt = preamble + "\n\n" + prompt

    research_questions = state.get("research_questions", [])
    output_focus = state.get("output_focus", "")
    if research_questions:
        prompt += "\n\n## Research Questions This Section Must Answer\n" + "\n".join(f"- {q}" for q in research_questions)
    if output_focus:
        prompt += f"\n\n## Output Focus\nPrioritize: {output_focus}"

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
    return {
        "findings": findings,
        "sufficiency_self_assessment": raw.get("sufficiency_self_assessment", ""),
    }


# ── Build the sub-graph (compiled once at module load) ──────────────────────

def _build_subgraph():
    builder = StateGraph(_CLState)
    builder.add_node("_discover", _discover)
    builder.add_node("_profile", _profile)
    builder.add_node("_generate_findings", _generate_findings)

    builder.add_edge(START, "_discover")
    builder.add_conditional_edges("_discover", _fanout)
    builder.add_edge("_profile", "_generate_findings")
    builder.add_edge("_generate_findings", END)

    return builder.compile()


_subgraph = _build_subgraph()


# ── Public entry point (called by section_router) ───────────────────────────

def run(section_spec: dict, scope: dict, scope_preamble: str = "") -> dict:
    """Run the competitive landscape sub-graph and return section findings."""
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
            "research_questions": section_spec.get("research_questions", []),
            "suggested_queries": section_spec.get("suggested_queries", []),
            "output_focus": section_spec.get("output_focus", ""),
            "minimum_evidence_threshold": section_spec.get("minimum_evidence_threshold", 5),
            "findings": [],
            "sufficiency_self_assessment": "",
        }
    )

    min_threshold = section_spec.get("minimum_evidence_threshold", 5)
    profile_count = len(result.get("profiles", []))
    if profile_count < min_threshold:
        logger.warning(
            "[competitive_landscape] profiles %d below threshold %d",
            profile_count, min_threshold,
        )

    section_id = section_spec["section_id"]
    seen_urls: set[str] = set()
    sources = []
    for profile in result.get("profiles", []):
        for url in profile.get("source_urls", []):
            if url and url not in seen_urls:
                seen_urls.add(url)
                sources.append(make_source(
                    url=url,
                    title=profile.get("name", ""),
                    section_id=section_id,
                    quality_tier="preferred",
                ))

    return {
        "sections": [
            make_section_findings(
                section_id=section_id,
                title=section_spec["title"],
                order=section_spec["order"],
                findings=result.get("findings", []),
                sources=sources,
                sufficiency_self_assessment=result.get("sufficiency_self_assessment", ""),
            )
        ]
    }
