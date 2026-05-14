import operator
from typing import Annotated, TypedDict


# ── Internal types (used by section sub-graphs) ─────────────────────────────

class CompetitorProfile(TypedDict):
    name: str
    positioning: str
    icp: str
    pricing: str
    differentiator: str
    source_urls: list[str]


# ── Top-level state ─────────────────────────────────────────────────────────

class ResearchScope(TypedDict):
    # Required
    industry: str
    geography: str

    # Optional — captured during intake when present
    user_role: str               # e.g., "CFO", "founder", "" if unknown
    decision_context: str        # e.g., "evaluating buy-vs-build", "" if unknown
    segment_focus: str           # e.g., "enterprise only", "" if unknown
    time_emphasis: str           # e.g., "last 6 months only", "" if unknown
    explicit_includes: list[str] # specific competitors / topics user wants covered
    explicit_excludes: list[str] # specific competitors / topics user wants skipped

    # Free-text catch-all
    additional_context: str

    # Internal — populated by intake before kickoff
    confirmation_summary: str    # what intake told the user before kicking off


def empty_scope() -> ResearchScope:
    """Return a blank scope with all fields initialised."""
    return {
        "industry": "",
        "geography": "",
        "user_role": "",
        "decision_context": "",
        "segment_focus": "",
        "time_emphasis": "",
        "explicit_includes": [],
        "explicit_excludes": [],
        "additional_context": "",
        "confirmation_summary": "",
    }


def render_scope_preamble(scope: ResearchScope) -> str:
    """Render the scope into a markdown preamble prepended to every section prompt.

    Returns empty string if no optional fields are set beyond industry/geography.
    """
    lines: list[str] = []
    lines.append("## User context for this report")
    lines.append("")
    lines.append(f"- Researching: {scope['industry']} in {scope['geography']}")

    if scope.get("user_role"):
        lines.append(f"- User's role/perspective: {scope['user_role']}")
    if scope.get("decision_context"):
        lines.append(f"- Decision being made: {scope['decision_context']}")
    if scope.get("segment_focus"):
        lines.append(f"- Segment focus: {scope['segment_focus']}")
    if scope.get("time_emphasis"):
        lines.append(f"- Time emphasis: {scope['time_emphasis']}")
    if scope.get("explicit_includes"):
        lines.append(f"- Must include: {', '.join(scope['explicit_includes'])}")
    if scope.get("explicit_excludes"):
        lines.append(f"- Must exclude: {', '.join(scope['explicit_excludes'])}")
    if scope.get("additional_context"):
        lines.append(f"- Additional context: {scope['additional_context']}")

    # Only return the preamble if there's something beyond the base line
    has_optional = any([
        scope.get("user_role"),
        scope.get("decision_context"),
        scope.get("segment_focus"),
        scope.get("time_emphasis"),
        scope.get("explicit_includes"),
        scope.get("explicit_excludes"),
        scope.get("additional_context"),
    ])

    if not has_optional:
        return ""

    lines.append("")
    lines.append("Tailor your research and analysis to this context. Specifically:")
    lines.append("- If a user role/perspective is given, frame analytical implications toward that perspective.")
    lines.append("- If a decision context is given, emphasize evidence that informs that decision.")
    lines.append("- If a segment focus is given, prioritize sources and competitors matching that segment.")
    lines.append("- If a time emphasis is given, weight sources accordingly.")
    lines.append("- Honor 'must include' and 'must exclude' lists strictly.")
    lines.append("")

    return "\n".join(lines)


class SectionTask(TypedDict):
    section_id: str
    title: str
    order: int
    research_questions: list[str]
    suggested_queries: list[str]
    source_priorities: list[str]
    geography_emphasis: str
    output_focus: str
    minimum_evidence_threshold: int


class ResearchBrief(TypedDict):
    overall_research_question: str
    sections: list[SectionTask]
    cross_section_themes: list[str]
    must_cover: list[str]
    must_avoid: list[str]
    persona_lens: str


# ── Structured findings (Phase B) ───────────────────────────────────────────

class Finding(TypedDict):
    id: str                                # e.g., "tr_001", "cl_003", "inv_002"
    headline: str                          # the claim, in one sentence
    evidence_summary: str                  # 2-4 sentences supporting the claim
    evidence_ids: list[str]                # references to specific evidence items
    confidence: str                        # "strong" | "moderate" | "weak_signal"
    relevant_to_other_sections: list[str]  # section_ids this finding may matter to


class Source(TypedDict):
    url: str
    title: str
    section_relevance: list[str]           # which section_ids this source is relevant to
    quality_tier: str                      # "preferred" | "general" | "low"


class SectionFindings(TypedDict):
    section_id: str
    title: str
    order: int
    findings: list[Finding]
    sources: list[Source]
    sufficiency_self_assessment: str       # subagent's read on whether research was adequate


class ResearchState(TypedDict):
    scope: ResearchScope
    scope_preamble: str                            # = research_brief.persona_lens
    research_brief: ResearchBrief                  # populated by Lead Researcher
    sections: Annotated[list[dict], operator.add]  # populated by Section Agents
    final_report: str                              # populated by Compiler
