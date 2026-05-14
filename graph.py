from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from nodes.compiler import compiler
from nodes.lead_researcher import lead_researcher
from nodes.sections import competitive_landscape, investment, trends
from state import ResearchState


def _section_router(state: dict) -> dict:
    """Dispatch to the correct section agent based on section_spec.section_id."""
    spec = state["section_spec"]
    scope = state["scope"]
    preamble = state.get("scope_preamble", "")
    section_id = spec["section_id"]

    if section_id == "competitive_landscape":
        return competitive_landscape.run(spec, scope, preamble)
    elif section_id == "trends":
        return trends.run(spec, scope, preamble)
    elif section_id == "investment":
        return investment.run(spec, scope, preamble)
    else:
        raise ValueError(f"Unknown section_id: {section_id}")


def _planner_fanout(state: ResearchState) -> list[Send]:
    """Emit one Send per SectionTask for parallel section execution."""
    return [
        Send("section_router", {
            "section_spec": task,
            "scope": state["scope"],
            "scope_preamble": state.get("scope_preamble", ""),
        })
        for task in state["research_brief"]["sections"]
    ]


def build_graph():
    builder = StateGraph(ResearchState)

    builder.add_node("lead_researcher", lead_researcher)
    builder.add_node("section_router", _section_router)
    builder.add_node("compiler", compiler)

    builder.add_edge(START, "lead_researcher")
    builder.add_conditional_edges("lead_researcher", _planner_fanout)
    builder.add_edge("section_router", "compiler")
    builder.add_edge("compiler", END)

    return builder.compile()
