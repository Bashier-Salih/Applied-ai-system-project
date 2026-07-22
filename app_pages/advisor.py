"""AI care advisor: grounded Q&A and interaction log.

Free-text pet-care Q&A, independent of any specific pet/schedule. This is
the "answer_question()" path in care_advisor/advisor.py: scope check ->
retrieve -> ask Claude -> grounding check -> confidence score -> log.
"""

import streamlit as st

from care_advisor.logging_store import read_recent
from ui import callout, get_advisor, render_advisor_response, section_label

section_label("Ask the AI care advisor")
st.caption(
    "Answers are grounded in a curated pet-care knowledge base: every claim "
    "must cite a source, and answers that can't be verified against a "
    "retrieved source are flagged rather than shown as fact. This is a "
    "general-care helper, not a diagnostic tool."
)
question = st.text_input(
    "Ask a pet-care question",
    value="How often should I brush a long-haired dog?",
    key="advisor_question",
)
if st.button("Ask", icon=":material/send:"):
    try:
        with st.spinner("Retrieving sources and asking the Care Advisor…"):
            response = get_advisor().answer_question(question)
        with st.container(border=True):
            render_advisor_response(response)
    except RuntimeError as e:
        callout("warning", str(e))

st.space("medium")

# Live view into logs/interactions.jsonl (written by CareAdvisor._log() on
# every call, including refusals) -- the audit trail for "why is this
# trustworthy": every AI interaction is recorded, not just the successful ones.
with st.expander("Recent AI interactions (log)", icon=":material/history:"):
    recent = read_recent(10)
    if recent:
        st.dataframe(
            [{
                "Time":       r.get("timestamp", "n/a")[:19].replace("T", " "),
                "Kind":       r.get("kind", "n/a"),
                "Query":      r.get("query", "n/a"),
                "Grounded":   "Yes" if r.get("grounded") else "No",
                "Confidence": r.get("confidence", "n/a"),
            } for r in recent],
            width="stretch", hide_index=True,
        )
    else:
        st.caption("No AI interactions logged yet.")
