import argparse

from dotenv import load_dotenv

load_dotenv()

import time  # noqa: E402

from graph import build_graph  # noqa: E402 — must come after load_dotenv
from state import empty_scope  # noqa: E402
from ui.history import save_run  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Market Research Agent — Competitor Snapshot")
    parser.add_argument("--industry", required=True, help='Industry or sector, e.g. "B2B sales enablement SaaS"')
    parser.add_argument("--geography", required=True, help='Geography, e.g. "India"')
    args = parser.parse_args()

    scope = empty_scope()
    scope["industry"] = args.industry
    scope["geography"] = args.geography

    graph = build_graph()
    initial = {
        "scope": scope,
        "scope_preamble": "",
        "research_brief": {
            "overall_research_question": "",
            "sections": [],
            "cross_section_themes": [],
            "must_cover": [],
            "must_avoid": [],
            "persona_lens": "",
        },
        "sections": [],
        "final_report": "",
    }

    start = time.time()
    result = graph.invoke(initial)
    elapsed = round(time.time() - start, 1)

    save_run(
        industry=args.industry,
        geography=args.geography,
        state=result,
        duration=elapsed,
    )


if __name__ == "__main__":
    main()
