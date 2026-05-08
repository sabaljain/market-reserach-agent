import json
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown

from state import ResearchState
from tools.llm import get_synth_llm

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "synthesize.md"
_console = Console()


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def synthesize_report(state: ResearchState) -> dict:
    industry = state["industry"]
    geography = state["geography"]
    profiles_json = json.dumps(state["profiles"], indent=2)
    also_considered = state.get("also_considered", [])
    also_considered_text = ", ".join(also_considered) if also_considered else "None"

    prompt = (
        _load_prompt()
        .replace("{industry}", industry)
        .replace("{geography}", geography)
        .replace("{profiles_json}", profiles_json)
        .replace("{also_considered}", also_considered_text)
    )

    client, deployment = get_synth_llm()
    response = client.chat.completions.create(
        model=deployment,
        max_completion_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    report = response.choices[0].message.content.strip()

    _console.print(Markdown(report))

    return {"report": report}
