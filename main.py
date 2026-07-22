from pawpal_system import Owner, Pet, Task, Scheduler
from formatting import (
    section_header, divider,
    format_schedule_table, format_filter_table,
    format_conflict_warnings, format_recurrence_event,
    format_next_slot,
)
from datetime import date

from care_advisor.advisor import CareAdvisor

# --- Setup ---
owner = Owner(name="Alex", available_hours=3)

biscuit = Pet(name="Biscuit", species="Dog", breed="Golden Retriever", age=4)
mochi   = Pet(name="Mochi",   species="Cat", breed="Scottish Fold",    age=2)

today = date.today()

# --- Tasks for Biscuit (added out of order intentionally) ---
biscuit.add_task(Task(name="Evening walk",    type="walk",       duration=30, priority="medium", preferred_time="17:00", recurrence="daily",  due_date=today))
biscuit.add_task(Task(name="Flea medication", type="meds",       duration=5,  priority="medium", preferred_time="09:00", due_time="10:00"))
biscuit.add_task(Task(name="Breakfast",       type="feeding",    duration=10, priority="high",   preferred_time="08:30", recurrence="daily",  due_date=today))
biscuit.add_task(Task(name="Morning walk",    type="walk",       duration=30, priority="high",   preferred_time="08:00", recurrence="daily",  due_date=today))

# --- Tasks for Mochi (added out of order intentionally) ---
mochi.add_task(Task(name="Playtime",  type="enrichment", duration=20, priority="medium", preferred_time="11:00", recurrence="weekly", due_date=today))
mochi.add_task(Task(name="Breakfast", type="feeding",    duration=5,  priority="high",   preferred_time="08:00", recurrence="daily",  due_date=today))
mochi.add_task(Task(name="Grooming",  type="grooming",   duration=15, priority="low",    preferred_time="10:00"))

# --- Register pets with owner ---
owner.add_pet(biscuit)
owner.add_pet(mochi)

# ── TODAY'S SCHEDULE ─────────────────────────────────────────────────────────
print(section_header(f"TODAY'S SCHEDULE FOR {owner.name.upper()}"))

schedulers = {}
for pet in owner.get_pets():
    scheduler = Scheduler(owner=owner, pet=pet)
    scheduler.generate_plan()
    schedulers[pet.name] = scheduler
    print(format_schedule_table(pet.name, pet.breed, scheduler.sort_by_time()))
    print()
    print(divider())

# ── CONFLICT DETECTION ────────────────────────────────────────────────────────
print(section_header("CONFLICT DETECTION"))

for pet_name, scheduler in schedulers.items():
    print(f"\n  Checking {pet_name}'s plan:")
    print(format_conflict_warnings(scheduler.detect_conflicts(), pet_name))

# Force a conflict for Rex to demo the warning path
rex = Pet(name="Rex", species="Dog", breed="Labrador", age=3)
rex.add_task(Task(name="Bath time",   type="grooming", duration=30, priority="high", scheduled_time="09:00"))
rex.add_task(Task(name="Vet checkup", type="medical",  duration=45, priority="high", scheduled_time="09:15"))
rex.add_task(Task(name="Lunch",       type="feeding",  duration=10, priority="medium", scheduled_time="12:00"))
owner.add_pet(rex)
rex_scheduler = Scheduler(owner=owner, pet=rex)
rex_scheduler.generated_plan = rex.tasks[:]

print(format_schedule_table(rex.name, rex.breed, rex_scheduler.generated_plan))
print()
print(f"\n  Checking Rex's plan:")
print(format_conflict_warnings(rex_scheduler.detect_conflicts(), rex.name))

# ── FILTER TASKS ──────────────────────────────────────────────────────────────
print(section_header("FILTER TASKS"))

print(format_filter_table(
    owner.filter_tasks(completed=False),
    "All pending tasks — all pets",
))
print(format_filter_table(
    owner.filter_tasks(pet_name="Biscuit"),
    "All tasks for Biscuit",
))

# ── RECURRENCE ────────────────────────────────────────────────────────────────
print(section_header("RECURRING TASK DEMO"))

morning_walk   = biscuit.tasks[3]
mochi_breakfast = mochi.tasks[1]
playtime        = mochi.tasks[0]

print()
next_walk      = biscuit.complete_task(morning_walk)
next_breakfast = mochi.complete_task(mochi_breakfast)
next_playtime  = mochi.complete_task(playtime)

for task, nxt in [(morning_walk, next_walk), (mochi_breakfast, next_breakfast), (playtime, next_playtime)]:
    print(format_recurrence_event(task, nxt))

print()
print(divider())

# ── FIND NEXT AVAILABLE SLOT ──────────────────────────────────────────────────
print(section_header("FIND NEXT AVAILABLE SLOT"))

for pet_name, scheduler in schedulers.items():
    for test_duration in [5, 20, 900]:
        slot = scheduler.find_next_slot(test_duration)
        print(format_next_slot(test_duration, slot, pet_name))
    print()

# ── AI CARE ADVISOR ────────────────────────────────────────────────────────────
print(section_header("AI CARE ADVISOR (RAG + guardrails demo)"))

advisor = CareAdvisor()
try:
    print("\n  Q: How often should I brush a long-haired dog?")
    answer = advisor.answer_question("How often should I brush a long-haired dog?")
    print(f"  A: {answer.answer}")
    print(f"     Confidence: {answer.confidence}/100  |  Grounded: {answer.grounding.grounded}")
    print(f"     Sources: {[r.chunk.id for r in answer.retrieved]}")

    print("\n  AI review of Biscuit's plan:")
    review = advisor.review_plan(schedulers["Biscuit"])
    print(f"  {review.answer}")
    print(f"     Confidence: {review.confidence}/100  |  Grounded: {review.grounding.grounded}")
except RuntimeError as e:
    print(f"\n  Skipped — {e}")

print()
print(divider())
