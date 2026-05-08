"""Chat session state management for the Streamlit UI."""

import streamlit as st

from state import ResearchScope, empty_scope

_INITIAL_MESSAGE = (
    "What market would you like researched? Tell me the industry and geography. "
    "Optionally share your role, what decision you're making, segment focus, or "
    "any other context that should shape the report — or just say 'go' if you "
    "want me to start with what you've given me."
)


def init_session_state() -> None:
    """Initialise session state keys if not already present."""
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": _INITIAL_MESSAGE, "type": "assistant"}
        ]
    if "scope" not in st.session_state:
        st.session_state.scope = empty_scope()
    if "phase" not in st.session_state:
        st.session_state.phase = "intake"  # "intake" | "researching" | "done"
    if "final_report" not in st.session_state:
        st.session_state.final_report = ""


def reset_session() -> None:
    """Reset to fresh intake state."""
    st.session_state.messages = [
        {"role": "assistant", "content": _INITIAL_MESSAGE, "type": "assistant"}
    ]
    st.session_state.scope = empty_scope()
    st.session_state.phase = "intake"
    st.session_state.final_report = ""


def add_message(role: str, content: str, msg_type: str | None = None) -> None:
    """Append a message to the chat history."""
    st.session_state.messages.append({
        "role": role,
        "content": content,
        "type": msg_type or role,
    })


def get_intake_history() -> list[dict]:
    """Return only user/assistant messages (not system_progress) for intake LLM."""
    return [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
        if m.get("type") in ("user", "assistant")
    ]
