import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

from nodes.intake import run_intake_turn
from ui.chat_state import (
    add_message,
    get_intake_history,
    init_session_state,
    reset_session,
)
from ui.streaming import run_research_with_callbacks

st.set_page_config(page_title="Market Research Agent", layout="wide")
init_session_state()

st.title("Market Research Agent")

# ── Sidebar: captured scope (debug) + reset button ───────────────────────────
with st.sidebar:
    with st.expander("Captured scope", expanded=False):
        st.json(st.session_state.scope)
    if st.session_state.phase == "done":
        if st.button("Research another market", type="primary"):
            reset_session()
            st.rerun()

# ── Render existing chat messages ────────────────────────────────────────────
for msg in st.session_state.messages:
    msg_type = msg.get("type", msg["role"])
    if msg_type == "system_progress":
        with st.chat_message("assistant"):
            st.caption(f"*{msg['content']}*")
    else:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

# ── Chat input ───────────────────────────────────────────────────────────────
phase = st.session_state.phase

if phase == "intake":
    if user_input := st.chat_input("Type your message..."):
        # Show user message
        add_message("user", user_input, "user")
        with st.chat_message("user"):
            st.markdown(user_input)

        # Run intake turn
        history = get_intake_history()
        scope, assistant_msg, ready = run_intake_turn(
            history, st.session_state.scope
        )
        st.session_state.scope = scope
        add_message("assistant", assistant_msg, "assistant")

        if ready:
            st.session_state.phase = "researching"

        st.rerun()

elif phase == "researching":
    st.chat_input("Research in progress...", disabled=True)

    # Run the research graph with progress callbacks
    progress_container = st.empty()

    def _on_progress(msg: str) -> None:
        add_message("assistant", msg, "system_progress")
        with progress_container.container():
            with st.chat_message("assistant"):
                st.caption(f"*{msg}*")

    result = run_research_with_callbacks(st.session_state.scope, _on_progress)

    # Add final report as assistant message
    final_report = result.get("final_report", "")
    st.session_state.final_report = final_report
    add_message("assistant", final_report, "assistant")
    st.session_state.phase = "done"
    st.rerun()

elif phase == "done":
    if user_input := st.chat_input("Type your message..."):
        add_message("user", user_input, "user")
        response = (
            "Follow-up questions on the report aren't supported yet. "
            "Click **Research another market** in the sidebar to start a new report."
        )
        add_message("assistant", response, "assistant")
        st.rerun()
