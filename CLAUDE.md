# Market Research Agent — v1 Competitor Snapshot

## Purpose
LangGraph pipeline: given an industry + geography, discovers 5–7 competitors, profiles each in parallel via web scraping + LLM, and synthesises a markdown report to the terminal.

## Run
```bash
python main.py --industry "B2B sales enablement SaaS" --geography "India"
```

## Stack
- **LangGraph** — orchestration (`StateGraph` + `Send` fanout)
- **Tavily** — web search (`tavily-python`)
- **requests + BeautifulSoup4** — homepage scraping
- **Azure AI Foundry (OpenAI endpoint)** — GPT-4.1-mini for discovery
- **Azure AI Foundry (Anthropic endpoint)** — Claude Sonnet 4.5 for profiling + synthesis
- **rich** — terminal markdown rendering

## Nodes
| Node | Model | Role |
|---|---|---|
| `discover_competitors` | GPT-4.1-mini | Searches Tavily, extracts deduplicated list of 5–7 company names |
| `profile_competitor` | Claude Sonnet 4.5 | Runs in parallel per company; scrapes homepage, extracts structured profile |
| `synthesize_report` | Claude Sonnet 4.5 | Combines all profiles into final markdown report |

## Required env vars (see `.env.example`)
- `TAVILY_API_KEY`
- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, `AZURE_API_VERSION`
- `AZURE_DEPLOYMENT_DISCOVERY` (GPT-4.1-mini deployment name)
- `AZURE_ANTHROPIC_ENDPOINT`, `AZURE_ANTHROPIC_KEY`
- `AZURE_DEPLOYMENT_PROFILER`, `AZURE_DEPLOYMENT_SYNTH` (Claude deployment names)

## Architecture notes
Prompts live in `prompts/*.md` — edit them without touching node code.
`ResearchState.profiles` uses `Annotated[list, operator.add]` so parallel profile nodes accumulate rather than overwrite.
In v2 this pipeline will be refactored toward a planner/section-researcher pattern (Report mAIstro style).
