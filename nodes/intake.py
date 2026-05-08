"""Intake agent — multi-turn LLM loop that builds a ResearchScope from chat.

NOT part of the LangGraph graph. Called directly from the Streamlit UI.
"""

import json
from pathlib import Path

from state import ResearchScope, empty_scope
from tools.llm import get_discovery_llm

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "intake_agent.md"


def run_intake_turn(
    message_history: list[dict],
    current_scope: ResearchScope,
) -> tuple[ResearchScope, str, bool]:
    """Run one turn of the intake conversation.

    Args:
        message_history: list of {"role": "user"|"assistant", "content": str}
        current_scope: the scope built so far

    Returns:
        (updated_scope, assistant_message, ready_to_research)
    """
    # Format message history for the prompt
    history_text = "\n".join(
        f"{msg['role'].capitalize()}: {msg['content']}" for msg in message_history
    )

    prompt = (
        _PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{message_history}", history_text)
    )

    client, deployment = get_discovery_llm()
    response = client.chat.completions.create(
        model=deployment,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    raw = response.choices[0].message.content.strip()
    # Strip markdown code fences if the model adds them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: return a safe response asking for clarification
        return current_scope, "I didn't quite catch that. Could you tell me what industry and geography you'd like me to research?", False

    # Extract updated scope
    scope_data = parsed.get("updated_scope", {})
    updated_scope: ResearchScope = {
        "industry": scope_data.get("industry", current_scope.get("industry", "")),
        "geography": scope_data.get("geography", current_scope.get("geography", "")),
        "user_role": scope_data.get("user_role", current_scope.get("user_role", "")),
        "decision_context": scope_data.get("decision_context", current_scope.get("decision_context", "")),
        "segment_focus": scope_data.get("segment_focus", current_scope.get("segment_focus", "")),
        "time_emphasis": scope_data.get("time_emphasis", current_scope.get("time_emphasis", "")),
        "explicit_includes": scope_data.get("explicit_includes", current_scope.get("explicit_includes", [])),
        "explicit_excludes": scope_data.get("explicit_excludes", current_scope.get("explicit_excludes", [])),
        "additional_context": scope_data.get("additional_context", current_scope.get("additional_context", "")),
        "confirmation_summary": scope_data.get("confirmation_summary", ""),
    }

    assistant_message = parsed.get("assistant_message", "Could you tell me more about what you'd like researched?")
    ready = parsed.get("ready_to_research", False)

    return updated_scope, assistant_message, ready
