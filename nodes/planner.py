from state import ResearchState, render_scope_preamble


def planner(state: ResearchState) -> dict:
    """Render scope preamble and emit section specs."""
    scope_preamble = render_scope_preamble(state["scope"])

    section_specs = [
        {"section_id": "competitive_landscape", "title": "Competitive Landscape",      "order": 0},
        {"section_id": "trends",                "title": "Market Trends",               "order": 1},
        {"section_id": "investment",            "title": "Investment & Funding Activity", "order": 2},
    ]
    return {"section_specs": section_specs, "scope_preamble": scope_preamble}
