"""Local result reranking — recovers ranking quality when the underlying
search provider doesn't supply a strong native relevance score.

Score = BM25(title + content vs query) + tier_bonus + preferred_domain_bonus

Tavily already returns a normalized 0–1 score; we keep its score if higher.
"""
from __future__ import annotations

from urllib.parse import urlparse

from rank_bm25 import BM25Okapi

_TIER_BONUS = {"preferred": 0.30, "general": 0.0, "low": -0.20}
_PREFERRED_DOMAIN_BONUS = 0.20


def _tokenize(text: str) -> list[str]:
    return [t for t in text.lower().split() if t]


def _domain_of(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""


def rerank(query: str, results: list[dict], preferred_domains: list[str] | None = None) -> list[dict]:
    """Return `results` sorted by composite score, descending.

    Mutates each result dict's `score` field with the new composite score
    when the new score exceeds the existing one (preserves Tavily's native
    score when it is already strong).
    """
    if not results:
        return results

    preferred_set = {d.lower().lstrip("www.") for d in (preferred_domains or [])}

    corpus = [_tokenize(f"{r.get('title', '')} {r.get('content', '')}") for r in results]
    bm25 = BM25Okapi(corpus) if any(corpus) else None
    query_tokens = _tokenize(query)

    raw_bm25 = bm25.get_scores(query_tokens) if bm25 else [0.0] * len(results)
    max_bm25 = max(raw_bm25) if len(raw_bm25) and max(raw_bm25) > 0 else 1.0

    for r, bm25_score in zip(results, raw_bm25):
        normalized_bm25 = bm25_score / max_bm25  # 0..1
        tier = _TIER_BONUS.get(r.get("source_quality", "general"), 0.0)
        domain_bonus = _PREFERRED_DOMAIN_BONUS if _domain_of(r.get("url", "")) in preferred_set else 0.0
        composite = normalized_bm25 + tier + domain_bonus
        existing = float(r.get("score") or 0.0)
        if composite > existing:
            r["score"] = composite

    return sorted(results, key=lambda r: float(r.get("score") or 0.0), reverse=True)
