import sys
import time
from pathlib import Path
from typing import Callable

# Ensure market_research_agent/ is importable regardless of how Streamlit resolves paths
sys.path.insert(0, str(Path(__file__).parent.parent))

from graph import build_graph  # noqa: E402
from state import ResearchScope  # noqa: E402

_NODE_LABELS = {
    "planner": "📋 Planning report sections...",
    "section_router": "🔬 Researching section...",
    "compiler": "✍️ Synthesizing final report...",
}


def run_research_with_callbacks(
    scope: ResearchScope,
    on_progress: Callable[[str], None],
) -> dict:
    """Run the research graph, calling on_progress(message) for each node event.

    Returns the final accumulated state dict.
    """
    graph = build_graph()
    initial = {
        "scope": scope,
        "scope_preamble": "",
        "section_specs": [],
        "sections": [],
        "final_report": "",
    }
    accumulated = dict(initial)
    start = time.time()

    for event in graph.stream(initial, stream_mode="updates"):
        node_name = next(iter(event))
        node_output = event[node_name]

        # Merge node output into accumulated state
        for key, value in node_output.items():
            if isinstance(value, list) and isinstance(accumulated.get(key), list):
                accumulated[key] = accumulated[key] + value
            else:
                accumulated[key] = value

        label = _NODE_LABELS.get(node_name, f"Running: {node_name}...")
        on_progress(label)

    elapsed = round(time.time() - start, 1)
    on_progress(f"✅ Done in {elapsed}s")
    return accumulated
