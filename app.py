import streamlit as st
from pawpal_system import Owner, Pet, Task, Scheduler
from formatting import task_emoji, RECURRENCE_SYMBOL, PRIORITY_COLOR
from datetime import date

from care_advisor.advisor import CareAdvisor
from care_advisor.retrieval import DocStore
from care_advisor.logging_store import read_recent

PRIORITY_BADGE = {"high": "🔴 High", "medium": "🟡 Medium", "low": "🟢 Low"}


@st.cache_resource
def get_advisor():
    """Cached across reruns so the TF-IDF index isn't rebuilt on every click."""
    return CareAdvisor(doc_store=DocStore())


def render_advisor_response(response):
    """Render an AdvisorResponse: answer, confidence badge, and sources."""
    if response.refused:
        st.warning(f"🚫 {response.answer}")
        return

    confidence = response.confidence
    if confidence >= 80:
        badge = f"🟢 Confidence: {confidence}/100 (grounded)"
    elif confidence >= 40:
        badge = f"🟡 Confidence: {confidence}/100"
    else:
        badge = f"🔴 Confidence: {confidence}/100 (weak or ungrounded)"

    st.markdown(response.answer)
    st.caption(badge)

    if response.grounding and not response.grounding.grounded:
        st.error(f"⚠️ Guardrail flag: {response.grounding.reason}")

    if response.retrieved:
        with st.expander(f"📚 Sources ({len(response.retrieved)})"):
            for r in response.retrieved:
                st.markdown(
                    f"**[{r.chunk.id}] {r.chunk.doc_title} — {r.chunk.heading}** "
                    f"(similarity: {r.score:.2f})\n\n{r.chunk.text}"
                )

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
st.title("🐾 PawPal+")
st.caption("A smart daily care planner for your pet.")

st.divider()

# ── Owner & Pet setup ────────────────────────────────────────────────────────
st.subheader("Owner & Pet Info")

col1, col2 = st.columns(2)
with col1:
    owner_name     = st.text_input("Owner name", value="Alex")
    available_hrs  = st.number_input("Available hours today", min_value=1, max_value=12, value=3)
with col2:
    pet_name  = st.text_input("Pet name", value="Biscuit")
    species   = st.selectbox("Species", ["Dog", "Cat", "Other"])
    breed     = st.text_input("Breed", value="Golden Retriever")

# Re-initialise session state whenever owner / pet identity changes
identity_key = (owner_name, available_hrs, pet_name, species, breed)
if st.session_state.get("_identity") != identity_key:
    st.session_state._identity = identity_key
    st.session_state.owner = Owner(name=owner_name, available_hours=available_hrs)
    st.session_state.pet   = Pet(name=pet_name, species=species, breed=breed, age=0)
    st.session_state.task_rows = []   # display-only list of dicts
    st.session_state.scheduler = None   # invalidate any previously generated plan

st.divider()

# ── Task entry ───────────────────────────────────────────────────────────────
st.subheader("Add a Task")

col1, col2, col3 = st.columns(3)
with col1:
    task_name  = st.text_input("Task name", value="Morning walk")
    task_type  = st.selectbox("Type", ["walk", "feeding", "meds", "grooming", "enrichment", "other"])
with col2:
    duration       = st.number_input("Duration (min)", min_value=1, max_value=240, value=30)
    priority       = st.selectbox("Priority", ["high", "medium", "low"])
with col3:
    preferred_time = st.text_input("Preferred time (HH:MM)", value="08:00")
    recurrence     = st.selectbox("Recurrence", ["none", "daily", "weekly"])

if st.button("➕ Add task"):
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
        "Task":       f"{task_emoji(task_type)}  {task_name}",
        "Type":       task_type,
        "Duration":   f"{duration} min",
        "Priority":   PRIORITY_BADGE[priority],
        "Preferred":  pref or "—",
        "Recurrence": RECURRENCE_SYMBOL.get(rec, "—"),
    })
    st.success(f"Added '{task_name}'")

if st.session_state.task_rows:
    st.dataframe(st.session_state.task_rows, use_container_width=True, hide_index=True)
else:
    st.info("No tasks yet. Add one above.")

st.divider()

# ── Generate schedule ────────────────────────────────────────────────────────
st.subheader("Generate Schedule")

if st.button("📅 Build today's plan"):
    pending = st.session_state.pet.get_pending_tasks()
    if not pending:
        st.warning("No pending tasks found. Add at least one task above.")
        st.session_state.scheduler = None
    else:
        scheduler = Scheduler(
            owner=st.session_state.owner,
            pet=st.session_state.pet,
        )
        scheduler.generate_plan()
        st.session_state.scheduler = scheduler

# Rendered from session_state (not just inside the button's `if`) so the plan
# survives the rerun triggered by clicking the AI Plan Review button below.
scheduler = st.session_state.get("scheduler")
if scheduler is not None:
    # ── Conflict warnings (deterministic, rule-based) ──────────────────────
    conflicts = scheduler.detect_conflicts()
    if conflicts:
        st.error(
            f"⚠️ **{len(conflicts)} scheduling conflict(s) detected** — "
            "review the warnings below before following this plan."
        )
        for warning in conflicts:
            # Strip the "WARNING: " prefix from the raw message
            friendly = warning.replace("WARNING: ", "")
            st.warning(f"🔴 {friendly}")
    else:
        st.success("✅ No conflicts — this plan is ready to follow!")

    # ── Sorted schedule table ─────────────────────────────────────────
    st.subheader(f"📋 {pet_name}'s Plan (sorted by time)")

    sorted_tasks = scheduler.sort_by_time()
    if sorted_tasks:
        rows = []
        for task in sorted_tasks:
            overdue = "⚠️ OVERDUE" if task.is_overdue() else "✓"
            rows.append({
                "Time":     task.scheduled_time,
                "Task":     f"{task_emoji(task.type)}  {task.name}",
                "Duration": f"{task.duration} min",
                "Priority": PRIORITY_BADGE[task.priority],
                "Recurs":   RECURRENCE_SYMBOL.get(task.recurrence, "—"),
                "Status":   overdue,
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No tasks could be scheduled within the available time budget.")

    # ── Reasoning ─────────────────────────────────────────────────────
    with st.expander("🧠 Why was the plan built this way?"):
        reasoning_lines = scheduler.get_reasoning().split("\n")
        for line in reasoning_lines[1:]:   # skip the header line
            st.markdown(line)

    # ── Find next available slot ──────────────────────────────────────
    st.divider()
    st.subheader("🕐 Find Next Available Slot")
    st.caption("Enter a task duration to find the earliest gap in today's plan.")
    slot_duration = st.number_input(
        "Task duration (min)", min_value=1, max_value=480, value=15, key="slot_dur"
    )
    slot = scheduler.find_next_slot(int(slot_duration))
    if slot:
        st.success(f"✅ Next available {slot_duration}-min slot: **{slot}**")
    else:
        st.warning(f"⚠️ No {slot_duration}-min gap available in today's plan.")

    # ── Completion status across all pets ─────────────────────────────
    st.divider()
    st.subheader("🔍 Task Filter")
    filter_status = st.radio(
        "Show tasks by status",
        ["All", "Pending only", "Completed only"],
        horizontal=True,
    )
    completed_map = {"All": None, "Pending only": False, "Completed only": True}
    filtered = st.session_state.owner.filter_tasks(
        completed=completed_map[filter_status],
        pet_name=pet_name,
    )
    if filtered:
        filter_rows = [{
            "Task":      f"{task_emoji(task.type)}  {task.name}",
            "Priority":  PRIORITY_BADGE[task.priority],
            "Due date":  str(task.due_date) if task.due_date else "—",
            "Recurs":    RECURRENCE_SYMBOL.get(task.recurrence, "—"),
            "Completed": "✓ done" if task.completed else "pending",
        } for _, task in filtered]
        st.dataframe(filter_rows, use_container_width=True, hide_index=True)
    else:
        st.info("No tasks match this filter.")

    # ── AI Plan Review (advisory only — never alters the plan above) ──────
    st.divider()
    st.subheader("🤖 AI Plan Review")
    st.caption(
        "Reviews the schedule above against a pet-care knowledge base for "
        "concerns the rule-based conflict check above can't see (timing, "
        "frequency, life-stage fit). This is advisory — it never changes "
        "the schedule or the conflict results above."
    )
    if st.button("Run AI care review"):
        try:
            with st.spinner("Reviewing schedule against the knowledge base…"):
                review = get_advisor().review_plan(scheduler)
            render_advisor_response(review)
        except RuntimeError as e:
            st.info(f"ℹ️ {e}")

st.divider()

# ── AI Care Advisor Q&A ───────────────────────────────────────────────────────
st.subheader("🩺 Ask the AI Care Advisor")
st.caption(
    "Answers are grounded in a curated pet-care knowledge base — every claim "
    "must cite a source, and answers that can't be verified against a "
    "retrieved source are flagged rather than shown as fact. This is a "
    "general-care helper, not a diagnostic tool."
)
question = st.text_input(
    "Ask a pet-care question",
    value="How often should I brush a long-haired dog?",
    key="advisor_question",
)
if st.button("Ask"):
    try:
        with st.spinner("Retrieving sources and asking the Care Advisor…"):
            response = get_advisor().answer_question(question)
        render_advisor_response(response)
    except RuntimeError as e:
        st.info(f"ℹ️ {e}")

with st.expander("🗂 Recent AI interactions (log)"):
    recent = read_recent(10)
    if recent:
        st.dataframe(
            [{
                "Time":       r.get("timestamp", "—")[:19].replace("T", " "),
                "Kind":       r.get("kind", "—"),
                "Query":      r.get("query", "—"),
                "Grounded":   "✓" if r.get("grounded") else "✗",
                "Confidence": r.get("confidence", "—"),
            } for r in recent],
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("No AI interactions logged yet.")
