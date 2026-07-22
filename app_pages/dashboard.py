"""Dashboard: action-first scheduler view.

Top row of action cards ("Add task" opens a modal dialog, "Build today's
plan" generates the schedule, plus an at-a-glance stats card), then the
generated plan, the next-slot / task-filter two-up, and the advisory-only
AI plan review. All scheduling logic (Owner / Pet / Task / Scheduler and
the session-state identity reset) is unchanged from the original app.
"""

from datetime import date

import streamlit as st

from pawpal_system import Owner, Pet, Task, Scheduler
from ui import (
    PRIORITY_LABEL,
    RECURRENCE_LABEL,
    callout,
    get_advisor,
    img_data_uri,
    render_advisor_response,
    section_label,
)

# ══════════════════════════════════════════════════════════════════════════
# Sidebar: global setup only (owner & pet identity)
# ══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    section_label("Owner &amp; pet")
    owner_name    = st.text_input("Owner name", value="Alex")
    available_hrs = st.number_input("Available hours today", min_value=1, max_value=12, value=3)
    pet_name = st.text_input("Pet name", value="Biscuit")
    species  = st.selectbox("Species", ["Dog", "Cat", "Other"])
    breed    = st.text_input("Breed", value="Golden Retriever")

    # Re-initialise session state whenever owner / pet identity changes
    identity_key = (owner_name, available_hrs, pet_name, species, breed)
    if st.session_state.get("_identity") != identity_key:
        st.session_state._identity = identity_key
        st.session_state.owner = Owner(name=owner_name, available_hours=available_hrs)
        st.session_state.pet   = Pet(name=pet_name, species=species, breed=breed, age=0)
        st.session_state.task_rows = []   # display-only list of dicts
        st.session_state.scheduler = None   # invalidate any previously generated plan

# ══════════════════════════════════════════════════════════════════════════
# Page header
# ══════════════════════════════════════════════════════════════════════════
dog = img_data_uri("dog.jpg")
cat = img_data_uri("cat.jpg")
st.markdown(
    f"""
    <div class="topbar">
        <div class="topbar-left">
            <span class="topbar-eyebrow">Dashboard</span>
            <span class="topbar-title">{pet_name}'s day</span>
            <span class="topbar-subtitle">Add tasks, build the plan, and let the advisor sanity-check it.</span>
        </div>
        <div class="topbar-avatars">
            <img src="{dog}" alt="Golden retriever" />
            <img src="{cat}" alt="Cat" />
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ══════════════════════════════════════════════════════════════════════════
# "Add task" modal dialog (replaces the old sidebar form)
# ══════════════════════════════════════════════════════════════════════════
@st.dialog("Add a task")
def add_task_dialog():
    with st.form("add_task_form", clear_on_submit=False, border=False):
        task_name = st.text_input("Task name", value="Morning walk")
        task_type = st.selectbox("Type", ["walk", "feeding", "meds", "grooming", "enrichment", "other"])
        duration  = st.number_input("Duration (min)", min_value=1, max_value=240, value=30)
        priority  = st.selectbox("Priority", ["high", "medium", "low"])
        preferred_time = st.text_input("Preferred time (HH:MM)", value="08:00")
        recurrence = st.selectbox("Recurrence", ["none", "daily", "weekly"])
        submitted = st.form_submit_button("Add task", width="stretch")

    if submitted:
        pref = preferred_time.strip() or None
        rec  = recurrence if recurrence != "none" else None
        task = Task(
            name=task_name,
            type=task_type,
            duration=int(duration),
            priority=priority,
            preferred_time=pref,
            recurrence=rec,
            due_date=date.today() if rec else None,
        )
        st.session_state.pet.add_task(task)
        st.session_state.task_rows.append({
            "Task":       task_name,
            "Type":       task_type,
            "Duration":   f"{duration} min",
            "Priority":   PRIORITY_LABEL[priority],
            "Preferred":  pref or "Any",
            "Recurrence": RECURRENCE_LABEL[rec],
        })
        st.rerun()   # close the dialog and refresh the dashboard


# ══════════════════════════════════════════════════════════════════════════
# Action cards
# ══════════════════════════════════════════════════════════════════════════
col_add, col_build, col_stats = st.columns([1, 1, 1.2])

with col_add:
    with st.container(border=True, height="stretch"):
        section_label("Add task")
        st.caption("Walks, meals, meds, grooming. One at a time.")
        if st.button("Add a task", icon=":material/add:", width="stretch"):
            add_task_dialog()

with col_build:
    with st.container(border=True, height="stretch"):
        section_label("Build plan")
        st.caption("Fit pending tasks into today's available hours.")
        if st.button("Build today's plan", icon=":material/event:", width="stretch"):
            pending = st.session_state.pet.get_pending_tasks()
            if not pending:
                st.session_state.scheduler = None
                st.session_state._build_error = True
            else:
                scheduler = Scheduler(
                    owner=st.session_state.owner,
                    pet=st.session_state.pet,
                )
                scheduler.generate_plan()
                st.session_state.scheduler = scheduler
                st.session_state._build_error = False

with col_stats:
    with st.container(border=True, height="stretch"):
        section_label("At a glance")
        s1, s2, s3 = st.columns(3)
        n_tasks = len(st.session_state.task_rows)
        planned = len(st.session_state.scheduler.sort_by_time()) if st.session_state.get("scheduler") else 0
        s1.markdown(
            f"<div class='stat-value'>{n_tasks}</div><div class='stat-label'>Tasks</div>",
            unsafe_allow_html=True,
        )
        s2.markdown(
            f"<div class='stat-value'>{planned}</div><div class='stat-label'>Planned</div>",
            unsafe_allow_html=True,
        )
        s3.markdown(
            f"<div class='stat-value'>{available_hrs}h</div><div class='stat-label'>Budget</div>",
            unsafe_allow_html=True,
        )

if st.session_state.get("_build_error"):
    callout("warning", "No pending tasks found. Add at least one task first.")

# Tasks added so far (compact, below the action row)
if st.session_state.task_rows:
    with st.expander(f"Tasks added so far ({len(st.session_state.task_rows)})"):
        st.dataframe(st.session_state.task_rows, width="stretch", hide_index=True)

# ══════════════════════════════════════════════════════════════════════════
# Generated plan, rendered from session_state so it survives reruns
# (including the rerun triggered by the AI review button below).
# ══════════════════════════════════════════════════════════════════════════
scheduler = st.session_state.get("scheduler")
if scheduler is not None:
    with st.container(border=True):
        # ── Conflict warnings (deterministic, rule-based) ──────────────────
        conflicts = scheduler.detect_conflicts()
        if conflicts:
            callout(
                "danger",
                f"<strong>{len(conflicts)} scheduling conflict(s) detected</strong>. "
                "Review before following this plan.",
            )
            for warning in conflicts:
                callout("warning", warning.replace("WARNING: ", ""))
        else:
            callout("good", "No conflicts. This plan is ready to follow.")

        # ── Sorted schedule table ──────────────────────────────────────────
        st.subheader(f"{pet_name}'s plan (sorted by time)")

        sorted_tasks = scheduler.sort_by_time()
        if sorted_tasks:
            rows = []
            for task in sorted_tasks:
                rows.append({
                    "Time":     task.scheduled_time,
                    "Task":     task.name,
                    "Type":     task.type,
                    "Duration": f"{task.duration} min",
                    "Priority": PRIORITY_LABEL[task.priority],
                    "Recurs":   RECURRENCE_LABEL.get(task.recurrence, "One-off"),
                    "Status":   "Overdue" if task.is_overdue() else "On track",
                })
            st.dataframe(rows, width="stretch", hide_index=True)
        else:
            st.caption("No tasks could be scheduled within the available time budget.")

        with st.expander("Why was the plan built this way?"):
            reasoning_lines = scheduler.get_reasoning().split("\n")
            for line in reasoning_lines[1:]:   # skip the header line
                st.markdown(line)

    # Asymmetric two-up layout (unequal widths, not a mirrored 50/50 split).
    col_slot, col_filter = st.columns([1.15, 1])

    with col_slot:
        with st.container(border=True):
            section_label("Next available slot")
            slot_duration = st.number_input(
                "Task duration (min)", min_value=1, max_value=480, value=15, key="slot_dur"
            )
            slot = scheduler.find_next_slot(int(slot_duration))
            if slot:
                callout("good", f"Next {slot_duration}-min slot: <strong>&nbsp;{slot}</strong>")
            else:
                callout("warning", f"No {slot_duration}-min gap available today.")

    with col_filter:
        with st.container(border=True):
            section_label("Task filter")
            filter_status = st.segmented_control(
                "Show tasks by status",
                ["All", "Pending only", "Completed only"],
                default="All",
            ) or "All"
            completed_map = {"All": None, "Pending only": False, "Completed only": True}
            filtered = st.session_state.owner.filter_tasks(
                completed=completed_map[filter_status],
                pet_name=pet_name,
            )
            if filtered:
                filter_rows = [{
                    "Task":      task.name,
                    "Priority":  PRIORITY_LABEL[task.priority],
                    "Due date":  str(task.due_date) if task.due_date else "None",
                    "Recurs":    RECURRENCE_LABEL.get(task.recurrence, "One-off"),
                    "Completed": "Done" if task.completed else "Pending",
                } for _, task in filtered]
                st.dataframe(filter_rows, width="stretch", hide_index=True)
            else:
                st.caption("No tasks match this filter.")

    # ── AI Plan Review (advisory only, never alters the plan above) ────────
    # This is the "review_plan()" path in care_advisor/advisor.py. It reads
    # the already-generated `scheduler` (same object the rule-based conflict
    # check above used) and asks Claude to flag care concerns the rule-based
    # scheduler has no knowledge of -- it never edits `scheduler` or its plan.
    section_label("AI plan review")
    st.caption(
        "Reviews the schedule above against a pet-care knowledge base for "
        "concerns the rule-based conflict check can't see (timing, "
        "frequency, life-stage fit). It is advisory only and never changes the plan."
    )
    if st.button("Run AI care review", icon=":material/fact_check:"):
        try:
            with st.spinner("Reviewing schedule against the knowledge base…"):
                review = get_advisor().review_plan(scheduler)
            with st.container(border=True):
                render_advisor_response(review)
        except RuntimeError as e:
            # Raised by CareAdvisor._ensure_client() when ANTHROPIC_API_KEY
            # isn't set -- shown as a friendly notice instead of a crash.
            callout("warning", str(e))
else:
    st.caption("Add a task, then click Build today's plan to get started.")
