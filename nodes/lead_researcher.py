"""Lead Researcher node.

Reads the full ResearchScope and produces a tailored ResearchBrief that
directs section agents with specific research questions, suggested queries,
source priorities, geography emphasis, and a persona lens.

On failure, falls back to the static planner to ensure graceful degradation.
"""

import json
import logging
from pathlib import Path

from nodes.planner import planner  # kept for fallback — do NOT delete planner.py
from state import ResearchBrief, ResearchState, SectionTask
from tools.llm import get_lead_researcher_llm

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "lead_researcher.md"
_ALLOWED_SECTION_IDS = {"competitive_landscape", "trends", "investment"}
_DEFAULT_THRESHOLD: dict[str, int] = {
    "competitive_landscape": 5,
    "trends": 8,
    "investment": 5,
}


def _call_llm(scope: dict) -> dict:
    prompt = _PROMPT_PATH.read_text(encoding="utf-8").replace(
        "{scope_json}", json.dumps(scope, indent=2)
    )
    client, deployment = get_lead_researcher_llm()
    response = client.chat.completions.create(
        model=deployment,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(response.choices[0].message.content)


def _validate_and_repair(raw: dict, scope: dict) -> ResearchBrief:
    geography = scope.get("geography", "")
    excludes = scope.get("explicit_excludes", [])

    # 1. Filter to allowed section_ids only
    sections: list[SectionTask] = []
    for s in raw.get("sections", []):
        sid = s.get("section_id", "")
        if sid not in _ALLOWED_SECTION_IDS:
            logger.warning("[lead_researcher] dropping unknown section_id=%r", sid)
            continue
        sections.append(s)

    # 2. Ensure competitive_landscape is present unless explicitly excluded
    present_ids = {s["section_id"] for s in sections}
    if "competitive_landscape" not in present_ids and "competitive_landscape" not in excludes:
        logger.warning("[lead_researcher] competitive_landscape missing; inserting default")
        sections.insert(0, {
            "section_id": "competitive_landscape",
            "title": "Competitive Landscape",
            "order": 0,
            "research_questions": [],
            "suggested_queries": [],
            "source_priorities": [],
            "geography_emphasis": f"Focus on players active in {geography}" if geography else "",
            "output_focus": "",
            "minimum_evidence_threshold": 5,
        })

    # 3. Re-index orders contiguously from 0
    sections.sort(key=lambda s: s.get("order", 99))
    for i, s in enumerate(sections):
        s["order"] = i

    # 4. Fill geography_emphasis where empty and geography is set
    if geography:
        for s in sections:
            if not s.get("geography_emphasis", "").strip():
                s["geography_emphasis"] = (
                    f"Weight findings toward {geography}; include local players and regional data."
                )

    # 5. Fill any missing optional fields with safe defaults
    for s in sections:
        s.setdefault("research_questions", [])
        s.setdefault("suggested_queries", [])
        s.setdefault("source_priorities", [])
        s.setdefault("output_focus", "")
        s.setdefault(
            "minimum_evidence_threshold",
            _DEFAULT_THRESHOLD.get(s["section_id"], 5),
        )

    return {
        "overall_research_question": raw.get("overall_research_question", ""),
        "sections": sections,
        "cross_section_themes": raw.get("cross_section_themes", []),
        "must_cover": raw.get("must_cover", []),
        "must_avoid": raw.get("must_avoid", []),
        "persona_lens": raw.get("persona_lens", ""),
    }


def lead_researcher(state: ResearchState) -> dict:
    scope = state["scope"]
    try:
        raw = _call_llm(scope)
        brief = _validate_and_repair(raw, scope)
        logger.info(
            "[lead_researcher] %d sections planned; overall_q=%r",
            len(brief["sections"]),
            brief["overall_research_question"][:80],
        )
        return {
            "research_brief": brief,
            "scope_preamble": brief["persona_lens"],
        }
    except Exception as exc:
        logger.error(
            "[lead_researcher] failed (%s); falling back to static planner", exc
        )
        fallback = planner(state)
        fallback_brief: ResearchBrief = {
            "overall_research_question": "",
            "sections": [
                {
                    "section_id": s["section_id"],
                    "title": s["title"],
                    "order": s["order"],
                    "research_questions": [],
                    "suggested_queries": [],
                    "source_priorities": [],
                    "geography_emphasis": "",
                    "output_focus": "",
                    "minimum_evidence_threshold": _DEFAULT_THRESHOLD.get(s["section_id"], 5),
                }
                for s in fallback["section_specs"]
            ],
            "cross_section_themes": [],
            "must_cover": [],
            "must_avoid": [],
            "persona_lens": fallback.get("scope_preamble", ""),
        }
        return {
            "research_brief": fallback_brief,
            "scope_preamble": fallback.get("scope_preamble", ""),
        }
