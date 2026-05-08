"""Per-section source quality profiles for Tavily domain-biased retrieval."""
from dataclasses import dataclass


@dataclass
class SourceProfile:
    preferred_domains: list[str]
    excluded_domains: list[str]


_UNIVERSAL_EXCLUDES = [
    "medium.com",
    "substack.com",
    "quora.com",
    "linkedin.com/pulse",
]

SECTION_PROFILES: dict[str, SourceProfile] = {
    "trends": SourceProfile(
        preferred_domains=[
            "gartner.com", "forrester.com", "idc.com",
            "mckinsey.com", "bcg.com", "bain.com",
            "deloitte.com", "pwc.com", "kpmg.com",
            "hbr.org", "mit.edu", "cbinsights.com",
        ],
        excluded_domains=_UNIVERSAL_EXCLUDES,
    ),
    "investment": SourceProfile(
        preferred_domains=[
            "crunchbase.com", "pitchbook.com", "dealroom.co",
            "tracxn.com", "sec.gov",
            "prnewswire.com", "businesswire.com",
            "bloomberg.com", "reuters.com", "ft.com", "wsj.com",
        ],
        excluded_domains=_UNIVERSAL_EXCLUDES,
    ),
    "competitive_landscape": SourceProfile(
        preferred_domains=[
            "g2.com", "capterra.com", "gartner.com",
            "crunchbase.com", "techcrunch.com",
        ],
        excluded_domains=_UNIVERSAL_EXCLUDES,
    ),
}

_GEOGRAPHY_DOMAINS: dict[str, list[str]] = {
    "india": [
        "inc42.com", "yourstory.com", "entrackr.com",
        "livemint.com", "economictimes.indiatimes.com", "business-standard.com",
    ],
    "usa": ["techcrunch.com", "axios.com", "venturebeat.com"],
    "uk": ["techmonitor.ai", "uktech.news", "cityam.com"],
    "europe": ["sifted.eu", "tech.eu"],
    "southeast asia": ["techinasia.com", "dealstreetasia.com", "kr-asia.com"],
    "china": ["36kr.com", "technode.com"],
    "latin america": ["latamlist.com", "contxto.com"],
}


def get_geography_domains(geography: str) -> list[str]:
    """Return geography-specific preferred domains.

    Matches on substring so "India" matches "india", "Southern India" etc.
    Returns [] for unrecognized geographies.
    """
    key = geography.lower().strip()
    for geo_key, domains in _GEOGRAPHY_DOMAINS.items():
        if geo_key in key or key in geo_key:
            return domains
    return []


def build_preferred(section_id: str, geography: str) -> list[str]:
    """Return the full preferred-domain list for a section + geography combo."""
    profile = SECTION_PROFILES.get(section_id)
    base = profile.preferred_domains if profile else []
    return base + get_geography_domains(geography)


def get_excluded(section_id: str) -> list[str]:
    """Return the excluded-domain list for a section."""
    profile = SECTION_PROFILES.get(section_id)
    return profile.excluded_domains if profile else _UNIVERSAL_EXCLUDES
