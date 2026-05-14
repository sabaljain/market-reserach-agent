# Market Research Agent — v1 Competitor Snapshot

## Purpose
LangGraph pipeline: given an industry + geography, discovers 5–7 competitors, profiles each in parallel via web scraping + LLM, and synthesises a markdown report to the terminal.

## Run
```bash
python main.py --industry "B2B sales enablement SaaS" --geography "India"
```

## Stack
- **LangGraph** — orchestration (`StateGraph` + `Send` fanout)
- **OpenSERP** (self-hosted Docker, default) — multi-engine SERP aggregation; Tavily kept as fallback via `SEARCH_PROVIDER=tavily`
- **rank-bm25** — local rerank to recover relevance ordering
- **requests + BeautifulSoup4** — homepage scraping
- **Azure AI Foundry (OpenAI endpoint)** — GPT-4.1-mini for discovery
- **Azure AI Foundry (Anthropic endpoint)** — Claude Sonnet 4.5 for profiling + synthesis
- **rich** — terminal markdown rendering

## Search architecture
`tools/search.py` exposes `search_tiered(...)` over a pluggable provider chosen by `SEARCH_PROVIDER` env var. Provider implementations live in `tools/providers/` (`tavily_provider.py`, `openserp_provider.py`). Results from all tiers are reranked by `tools/rerank.py` (BM25 + domain-tier bonus) before return. To run with OpenSERP:

```bash
docker compose -f docker-compose.openserp.yml up -d
python main.py --industry "..." --geography "..."
```

## Nodes
| Node | Model | Role |
|---|---|---|
| `discover_competitors` | GPT-4.1-mini | Searches Tavily, extracts deduplicated list of 5–7 company names |
| `profile_competitor` | Claude Sonnet 4.5 | Runs in parallel per company; scrapes homepage, extracts structured profile |
| `synthesize_report` | Claude Sonnet 4.5 | Combines all profiles into final markdown report |

## Required env vars (see `.env.example`)
- `SEARCH_PROVIDER` (default `openserp`; alternative `tavily`)
- `OPENSERP_URL` (default `http://localhost:7000`)
- `TAVILY_API_KEY` (only if `SEARCH_PROVIDER=tavily`)
- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, `AZURE_API_VERSION`
- `AZURE_DEPLOYMENT_DISCOVERY` (GPT-4.1-mini deployment name)
- `AZURE_ANTHROPIC_ENDPOINT`, `AZURE_ANTHROPIC_KEY`
- `AZURE_DEPLOYMENT_PROFILER`, `AZURE_DEPLOYMENT_SYNTH` (Claude deployment names)

## Architecture notes
Prompts live in `prompts/*.md` — edit them without touching node code.
`ResearchState.profiles` uses `Annotated[list, operator.add]` so parallel profile nodes accumulate rather than overwrite.
In v2 this pipeline will be refactored toward a planner/section-researcher pattern (Report mAIstro style).
