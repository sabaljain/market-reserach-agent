from typing import TypedDict

from state import Finding, SectionFindings, Source


class SectionResult(TypedDict):
    """Deprecated — kept for fallback compatibility. Use SectionFindings instead."""
    section_id: str
    title: str
    order: int
    markdown: str
    sources: list[str]


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


def make_section_findings(
    section_id: str,
    title: str,
    order: int,
    findings: list[Finding],
    sources: list[Source],
    sufficiency_self_assessment: str,
) -> SectionFindings:
    return {
        "section_id": section_id,
        "title": title,
        "order": order,
        "findings": findings,
        "sources": sources,
        "sufficiency_self_assessment": sufficiency_self_assessment,
    }


def make_source(
    url: str,
    title: str,
    section_id: str,
    quality_tier: str = "general",
) -> Source:
    return {
        "url": url,
        "title": title,
        "section_relevance": [section_id],
        "quality_tier": quality_tier,
    }
