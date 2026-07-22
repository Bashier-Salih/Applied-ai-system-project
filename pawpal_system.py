from dataclasses import dataclass, field, replace
from typing import Optional
from datetime import datetime, timedelta, date


PRIORITY_ORDER  = {"high": 1, "medium": 2, "low": 3}
RECURRENCE_DAYS = {"daily": 1, "weekly": 7}


@dataclass
class Task:
    name: str
    type: str
    duration: int        # minutes
    priority: str        # "high", "medium", "low"
    preferred_time: Optional[str] = None   # "HH:MM" or None
    due_time: Optional[str] = None         # "HH:MM" or None
    scheduled_time: Optional[str] = None   # assigned by Scheduler
    completed: bool = False
    recurrence: Optional[str] = None       # "daily", "weekly", or None
    due_date: Optional[date] = None        # calendar date this occurrence is due

    def mark_complete(self) -> Optional["Task"]:
        """Mark this task as completed. Returns the next occurrence if recurrent, else None."""
        self.completed = True
        days = RECURRENCE_DAYS.get(self.recurrence)
        if days is None:
            return None
        base = self.due_date or date.today()
        return replace(self, completed=False, scheduled_time=None, due_date=base + timedelta(days=days))

    def is_overdue(self) -> bool:
        """Return True if the task was scheduled after its due time."""
        if not self.due_time or not self.scheduled_time:
            return False
        fmt = "%H:%M"
        return datetime.strptime(self.scheduled_time, fmt) > datetime.strptime(self.due_time, fmt)

    def update(self, **kwargs):
        """Update any task attribute by keyword argument."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)


@dataclass
class Pet:
    name: str
    species: str
    breed: str
    age: int
    tasks: list = field(default_factory=list)

    def add_task(self, task: Task):
        """Add a task to this pet's task list."""
        self.tasks.append(task)

    def remove_task(self, task: Task):
        """Remove a task from this pet's task list."""
        self.tasks.remove(task)

    def get_tasks(self) -> list:
        """Return all tasks for this pet."""
        return self.tasks

    def get_pending_tasks(self) -> list:
        """Return only tasks that have not been completed."""
        return [t for t in self.tasks if not t.completed]

    def complete_task(self, task: Task) -> Optional[Task]:
        """Mark a task complete and auto-append the next occurrence if it recurs.

        Calls task.mark_complete(), which sets completed=True and, for recurring
        tasks, returns a fresh Task with a new due_date advanced by the recurrence
        interval (1 day for "daily", 7 days for "weekly"). That next occurrence is
        appended to this pet's task list automatically so it will appear in future
        generated plans without any extra calls from the caller.

        Args:
            task: A Task that belongs to this pet's task list.

        Returns:
            The newly created next-occurrence Task if the task recurs, else None.
        """
        next_task = task.mark_complete()
        if next_task:
            self.tasks.append(next_task)
        return next_task


class Owner:
    def __init__(self, name: str, available_hours: int):
        self.name = name
        self.available_hours = available_hours
        self.pets = []

    def add_pet(self, pet: Pet):
        """Register a pet with this owner."""
        self.pets.append(pet)

    def get_pets(self) -> list:
        """Return all pets belonging to this owner."""
        return self.pets

    def get_all_tasks(self) -> list:
        """Retrieve all pending tasks across every pet the owner has."""
        all_tasks = []
        for pet in self.pets:
            for task in pet.get_pending_tasks():
                all_tasks.append((pet, task))
        return all_tasks

    def filter_tasks(self, completed: Optional[bool] = None, pet_name: Optional[str] = None) -> list:
        """Return (pet, task) pairs filtered by completion status and/or pet name.

        Both parameters are optional. Omitting one skips that filter entirely,
        so calling filter_tasks() with no arguments returns every task across all
        pets. Pet name matching is case-insensitive. The method searches all tasks
        on each pet (not just pending ones), so completed=True correctly surfaces
        finished tasks.

        Args:
            completed: If True, include only completed tasks. If False, include
                only pending tasks. If None (default), include tasks regardless
                of completion status.
            pet_name: If provided, include only tasks belonging to the pet whose
                name matches this string (case-insensitive). If None (default),
                include tasks from all pets.

        Returns:
            A list of (Pet, Task) tuples matching all supplied filters.
        """
        return [
            (pet, task)
            for pet in self.pets
            if pet_name is None or pet.name.lower() == pet_name.lower()
            for task in pet.tasks
            if completed is None or task.completed == completed
        ]


class Scheduler:
    def __init__(self, owner: Owner, pet: Pet, start_time: str = "08:00"):
        self.owner = owner
        self.pet = pet
        self.daily_time_budget = owner.available_hours * 60  # convert to minutes
        self.start_time = start_time
        self.generated_plan = []

    def prioritize_tasks(self) -> list:
        """Sort pending tasks by priority then by preferred_time."""
        tasks = self.pet.get_pending_tasks()
        return sorted(tasks, key=lambda t: (
            PRIORITY_ORDER.get(t.priority, 99),
            t.preferred_time or "99:99"
        ))

    def assign_time_slots(self):
        """Walk through prioritized tasks and assign a start time to each that fits the budget."""
        current = datetime.strptime(self.start_time, "%H:%M")
        time_used = 0
        self.generated_plan = []

        for task in self.prioritize_tasks():
            if time_used + task.duration > self.daily_time_budget:
                break
            task.scheduled_time = current.strftime("%H:%M")
            self.generated_plan.append(task)
            current += timedelta(minutes=task.duration)
            time_used += task.duration

    def detect_conflicts(self) -> list:
        """Return a list of warning strings for any overlapping tasks in the plan.

        Compares every pair of scheduled tasks using interval overlap arithmetic:
        two tasks conflict when one starts before the other ends. Each task's
        "HH:MM" scheduled_time is converted to total minutes for integer
        comparison, avoiding datetime parsing overhead. Tasks without a
        scheduled_time are skipped. The method never raises — callers receive
        an empty list when the plan is clean.

        Returns:
            A list of human-readable warning strings, one per conflicting pair.
            Empty if no overlaps exist.
        """
        def to_minutes(hhmm: str) -> int:
            h, m = map(int, hhmm.split(":"))
            return h * 60 + m

        warnings = []
        tasks = [t for t in self.generated_plan if t.scheduled_time]

        for i in range(len(tasks)):
            for j in range(i + 1, len(tasks)):
                a, b = tasks[i], tasks[j]
                a_start, b_start = to_minutes(a.scheduled_time), to_minutes(b.scheduled_time)
                a_end,   b_end   = a_start + a.duration,          b_start + b.duration
                if a_start < b_end and b_start < a_end:
                    warnings.append(
                        f"WARNING: '{a.name}' ({a.scheduled_time}, {a.duration} min) "
                        f"overlaps with '{b.name}' ({b.scheduled_time}, {b.duration} min) "
                        f"for {self.pet.name}"
                    )
        return warnings

    def find_next_slot(self, duration: int) -> Optional[str]:
        """Return the earliest gap in the plan where a task of `duration` minutes fits.

        Scans the generated plan as a sequence of occupied intervals and finds
        the first opening where `duration` minutes of free time exist. Three
        gap positions are checked in order:

        1. Before the first scheduled task (between start_time and task 0).
        2. Between every consecutive pair of tasks.
        3. After the last task, up to midnight (23:59).

        Each "HH:MM" scheduled_time is converted to integer minutes for
        arithmetic; the result is converted back to "HH:MM" before returning.

        Args:
            duration: Required length of the task in minutes.

        Returns:
            The earliest available start time as "HH:MM", or None if no gap
            large enough exists within the day.
        """
        def to_minutes(hhmm: str) -> int:
            h, m = map(int, hhmm.split(":"))
            return h * 60 + m

        def to_hhmm(minutes: int) -> str:
            return f"{minutes // 60:02d}:{minutes % 60:02d}"

        scheduled = sorted(
            [t for t in self.generated_plan if t.scheduled_time],
            key=lambda t: to_minutes(t.scheduled_time),
        )

        day_start = to_minutes(self.start_time)
        day_end   = 23 * 60 + 59   # latest returnable slot start

        if not scheduled:
            return to_hhmm(day_start) if duration <= day_end - day_start else None

        # Gap before the first task
        first_start = to_minutes(scheduled[0].scheduled_time)
        if first_start - day_start >= duration:
            return to_hhmm(day_start)

        # Gaps between consecutive tasks
        for i in range(len(scheduled) - 1):
            gap_start = to_minutes(scheduled[i].scheduled_time) + scheduled[i].duration
            gap_end   = to_minutes(scheduled[i + 1].scheduled_time)
            if gap_end - gap_start >= duration:
                return to_hhmm(gap_start)

        # Gap after the last task
        after_last = to_minutes(scheduled[-1].scheduled_time) + scheduled[-1].duration
        if day_end - after_last >= duration:
            return to_hhmm(after_last)

        return None

    def sort_by_time(self) -> list:
        """Return scheduled tasks sorted by scheduled_time in HH:MM order.

        Uses Python's sorted() with a lambda key that extracts scheduled_time
        directly as a string. Because the format is zero-padded "HH:MM",
        lexicographic string order equals chronological order with no parsing
        required. Tasks without a scheduled_time are excluded. The original
        generated_plan list is not modified.

        Returns:
            A new list of Task objects ordered from earliest to latest
            scheduled_time.
        """
        return sorted(
            [t for t in self.generated_plan if t.scheduled_time],
            key=lambda t: t.scheduled_time
        )

    def generate_plan(self) -> list:
        """Build and return the full daily plan for the pet."""
        self.assign_time_slots()
        return self.generated_plan

    def display_plan(self) -> str:
        """Return a formatted string of the scheduled plan."""
        if not self.generated_plan:
            return "No plan generated yet. Call generate_plan() first."
        lines = [f"Daily plan for {self.pet.name} ({self.pet.breed}):"]
        for task in self.generated_plan:
            overdue_flag = " [OVERDUE]" if task.is_overdue() else ""
            lines.append(
                f"  {task.scheduled_time} — {task.name} ({task.duration} min)"
                f" [priority: {task.priority}]{overdue_flag}"
            )
        return "\n".join(lines)

    def get_reasoning(self) -> str:
        """Explain why each task was scheduled in its position."""
        if not self.generated_plan:
            return "No plan generated yet. Call generate_plan() first."
        lines = [f"Reasoning for {self.pet.name}'s plan:"]
        for i, task in enumerate(self.generated_plan, 1):
            lines.append(
                f"  {i}. '{task.name}' scheduled at {task.scheduled_time} "
                f"because it has {task.priority} priority"
                + (f" and preferred time {task.preferred_time}." if task.preferred_time else ".")
            )
        scheduled_ids = {id(t) for t in self.generated_plan}
        skipped = [t for t in self.pet.get_pending_tasks() if id(t) not in scheduled_ids]
        if skipped:
            skipped_names = ", ".join(t.name for t in skipped)
            lines.append(f"  Skipped (exceeded time budget): {skipped_names}")
        return "\n".join(lines)
