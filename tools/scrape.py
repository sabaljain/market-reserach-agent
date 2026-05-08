import requests
from bs4 import BeautifulSoup

try:
    from langsmith import traceable
except ImportError:
    def traceable(**_kw):  # type: ignore[misc]
        return lambda f: f


@traceable(name="scrape_page", run_type="tool")
def scrape_page(url: str, char_limit: int = 8000) -> str:
    """Fetch a URL and return clean body text, capped at char_limit characters."""
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        return text[:char_limit]
    except Exception:
        return ""
