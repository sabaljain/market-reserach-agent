import argparse

from dotenv import load_dotenv

load_dotenv()

from graph import build_graph  # noqa: E402 — must come after load_dotenv
from state import empty_scope  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Market Research Agent — Competitor Snapshot")
    parser.add_argument("--industry", required=True, help='Industry or sector, e.g. "B2B sales enablement SaaS"')
    parser.add_argument("--geography", required=True, help='Geography, e.g. "India"')
    args = parser.parse_args()

    scope = empty_scope()
    scope["industry"] = args.industry
    scope["geography"] = args.geography

    graph = build_graph()
    graph.invoke(
        {
            "scope": scope,
            "scope_preamble": "",
            "section_specs": [],
            "sections": [],
            "final_report": "",
        }
    )


if __name__ == "__main__":
    main()
