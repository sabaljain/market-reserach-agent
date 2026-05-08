from typing import TypedDict


class SectionResult(TypedDict):
    section_id: str       # e.g., "competitive_landscape"
    title: str            # e.g., "Competitive Landscape"
    order: int            # display order in the final report (0-indexed)
    markdown: str         # the section's body
    sources: list[str]    # URLs cited


def make_section_result(
    section_id: str,
    title: str,
    order: int,
    markdown: str,
    sources: list[str],
) -> SectionResult:
    return {
        "section_id": section_id,
        "title": title,
        "order": order,
        "markdown": markdown,
        "sources": sources,
    }
