"""PawPal+ entry point.

Defines the 3-page navigation (Landing / Dashboard / AI advisor), injects the
shared design system, and initialises the session state every page relies on.
Run with:  streamlit run app.py
"""

import streamlit as st

from ui import inject_css

st.set_page_config(page_title="PawPal+", page_icon=":material/pets:", layout="wide")

inject_css()

# ── Shared per-user state ────────────────────────────────────────────────────
# Initialised here (the entry file runs before every page) so any page can
# read it. The actual Owner/Pet objects are (re)built by the dashboard's
# sidebar whenever the identity fields change; see app_pages/dashboard.py.
if "task_rows" not in st.session_state:
    st.session_state.task_rows = []      # display-only list of dicts
if "scheduler" not in st.session_state:
    st.session_state.scheduler = None    # last generated plan (survives reruns)

# ── Navigation ───────────────────────────────────────────────────────────────
page = st.navigation(
    [
        st.Page("app_pages/landing.py", title="Home", icon=":material/home:", default=True),
        st.Page("app_pages/dashboard.py", title="Dashboard", icon=":material/dashboard:"),
        st.Page("app_pages/advisor.py", title="AI advisor", icon=":material/psychology:"),
    ],
    position="top",
)
page.run()
