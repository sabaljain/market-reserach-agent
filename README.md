# Market Research Agent — v1 Competitor Snapshot

A LangGraph pipeline that takes an industry and geography, discovers 5–7 competitors, profiles each in parallel via web scraping + LLM, and prints a markdown report to the terminal.

## Prerequisites

- Python 3.11+
- A [Tavily](https://tavily.com) API key (free tier works)
- An Azure AI Foundry workspace with:
  - A GPT-4.1-mini deployment (for discovery)
  - A Claude Sonnet 4.5 deployment via the Anthropic serverless endpoint (for profiling + synthesis)

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create your .env file
cp .env.example .env
# Fill in your API keys and deployment names in .env
```

## Running

**Terminal (CLI):**
```bash
python main.py --industry "B2B sales enablement SaaS" --geography "India"
```

**Streamlit UI (testing/debugging):**
```bash
streamlit run app.py
```
Opens at `http://localhost:8501`. The UI streams node progress, shows per-competitor profiles in expandable panels, and persists the last 5 runs in `run_history/` for prompt iteration comparison.

## Configuration

All config is via `.env`. To swap models, change the deployment name env vars — no code changes needed:

| Env var | Default | Node |
|---|---|---|
| `AZURE_DEPLOYMENT_DISCOVERY` | `gpt-4.1-mini` | discover_competitors |
| `AZURE_DEPLOYMENT_PROFILER` | `claude-sonnet-4-5` | profile_competitor |
| `AZURE_DEPLOYMENT_SYNTH` | `claude-sonnet-4-5` | synthesize_report |

## File structure

```
market_research_agent/
├── main.py              # CLI entry point
├── graph.py             # LangGraph wiring
├── state.py             # ResearchState TypedDict
├── nodes/
│   ├── discover.py      # discover_competitors node
│   ├── profile.py       # profile_competitor node + Send fanout
│   └── synthesize.py    # synthesize_report node
├── tools/
│   ├── llm.py           # Azure client factories
│   ├── search.py        # Tavily wrapper
│   └── scrape.py        # requests + BeautifulSoup wrapper
└── prompts/
    ├── discover.md      # competitor extraction prompt
    ├── profile.md       # per-company extraction prompt
    └── synthesize.md    # final report prompt
```

## Dry-run (no API keys needed)

```bash
python -c "from graph import build_graph; build_graph(); print('Graph compiled OK')"
```
