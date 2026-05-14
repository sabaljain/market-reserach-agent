"""Search provider implementations.

Each provider exposes a `raw_search(...)` function returning a list of result
dicts with the canonical shape:
    {title, url, content, score, published_date}

The active provider is selected via the SEARCH_PROVIDER env var; see
`tools.search.get_provider`.
"""
