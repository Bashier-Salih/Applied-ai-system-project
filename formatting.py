"""
CLI formatting helpers for PawPal+.

Uses `tabulate` for structured tables and `colorama` for ANSI color output.
All public functions accept plain data and return formatted strings so the
display logic stays out of the core scheduling classes.
"""

from tabulate import tabulate
from colorama import init, Fore, Style

init(autoreset=True)   # reset color codes after every print automatically

# ── Task type → emoji ────────────────────────────────────────────────────────
TASK_EMOJI = {
    "walk":       "🦮",
    "feeding":    "🍽️",
    "meds":       "💊",
    "grooming":   "✂️",
    "enrichment": "🎾",
    "medical":    "🏥",
    "general":    "📋",
}

# ── Priority → color ─────────────────────────────────────────────────────────
PRIORITY_COLOR = {
    "high":   Fore.RED,
    "medium": Fore.YELLOW,
    "low":    Fore.GREEN,
}

# ── Recurrence → symbol ──────────────────────────────────────────────────────
RECURRENCE_SYMBOL = {
    "daily":  "🔁 daily",
    "weekly": "📅 weekly",
}


def task_emoji(task_type: str) -> str:
    """Return the emoji for a task type, falling back to 📋."""
    return TASK_EMOJI.get(task_type, "📋")


def priority_badge(priority: str) -> str:
    """Return a color-coded priority label using ANSI codes."""
    color = PRIORITY_COLOR.get(priority, "")
    return f"{color}{priority.upper()}{Style.RESET_ALL}"


def section_header(title: str) -> str:
    """Return a bold, cyan section header string."""
    bar = "=" * 47
    return f"\n{Fore.CYAN}{Style.BRIGHT}{bar}\n  {title}\n{bar}{Style.RESET_ALL}"


def divider() -> str:
    """Return a dim horizontal rule."""
    return f"{Style.DIM}{'─' * 47}{Style.RESET_ALL}"


def format_schedule_table(pet_name: str, breed: str, tasks: list) -> str:
    """Return a tabulate table of scheduled tasks for one pet.

    Args:
        pet_name: Display name of the pet.
        breed:    Breed string shown in the header.
        tasks:    List of Task objects with scheduled_time assigned.

    Returns:
        A formatted string containing a header and a plain-text table.
    """
    header = (
        f"\n{Fore.MAGENTA}{Style.BRIGHT}🐾  {pet_name}"
        f"{Style.NORMAL} ({breed}){Style.RESET_ALL}"
    )
    rows = []
    for task in tasks:
        overdue = f" {Fore.RED}⚠ OVERDUE{Style.RESET_ALL}" if task.is_overdue() else ""
        rows.append([
            f"{Fore.WHITE}{task.scheduled_time}{Style.RESET_ALL}",
            f"{task_emoji(task.type)}  {task.name}{overdue}",
            f"{task.duration} min",
            priority_badge(task.priority),
            RECURRENCE_SYMBOL.get(task.recurrence, "—"),
        ])
    table = tabulate(
        rows,
        headers=["Time", "Task", "Duration", "Priority", "Recurs"],
        tablefmt="rounded_outline",
    )
    return f"{header}\n{table}"


def format_filter_table(pairs: list, title: str) -> str:
    """Return a tabulate table from a list of (Pet, Task) filter results.

    Args:
        pairs: List of (Pet, Task) tuples as returned by Owner.filter_tasks().
        title: Section label printed above the table.

    Returns:
        A formatted string with title and table, or a notice if pairs is empty.
    """
    if not pairs:
        return f"  {Style.DIM}(no results){Style.RESET_ALL}"
    rows = []
    for pet, task in pairs:
        status = (
            f"{Fore.GREEN}✓ done{Style.RESET_ALL}"
            if task.completed
            else f"{Fore.YELLOW}pending{Style.RESET_ALL}"
        )
        due = str(task.due_date) if task.due_date else "—"
        rows.append([
            pet.name,
            f"{task_emoji(task.type)}  {task.name}",
            priority_badge(task.priority),
            RECURRENCE_SYMBOL.get(task.recurrence, "—"),
            due,
            status,
        ])
    table = tabulate(
        rows,
        headers=["Pet", "Task", "Priority", "Recurs", "Due date", "Status"],
        tablefmt="rounded_outline",
    )
    return f"\n{Fore.WHITE}{Style.BRIGHT}{title}{Style.RESET_ALL}\n{table}"


def format_conflict_warnings(conflicts: list, pet_name: str) -> str:
    """Return color-coded conflict warning lines or a clean-plan message.

    Args:
        conflicts: List of warning strings from Scheduler.detect_conflicts().
        pet_name:  Name of the pet whose plan was checked.

    Returns:
        A formatted string — red warnings if conflicts exist, green otherwise.
    """
    if not conflicts:
        return f"  {Fore.GREEN}✅  No conflicts — {pet_name}'s plan is clean.{Style.RESET_ALL}"
    lines = [f"  {Fore.RED}{Style.BRIGHT}⚠  {len(conflicts)} conflict(s) detected:{Style.RESET_ALL}"]
    for w in conflicts:
        friendly = w.replace("WARNING: ", "")
        lines.append(f"  {Fore.RED}•  {friendly}{Style.RESET_ALL}")
    return "\n".join(lines)


def format_next_slot(duration: int, slot: str | None, pet_name: str) -> str:
    """Return a formatted message for a find_next_slot() result.

    Args:
        duration:  The requested task duration in minutes.
        slot:      The "HH:MM" result from find_next_slot(), or None.
        pet_name:  Name of the pet whose plan was searched.

    Returns:
        A color-coded one-line string indicating the found slot or no availability.
    """
    if slot:
        return (
            f"  {Fore.CYAN}🕐  Next available {duration}-min slot "
            f"for {pet_name}: {Style.BRIGHT}{slot}{Style.RESET_ALL}"
        )
    return (
        f"  {Fore.RED}✗  No {duration}-min slot available "
        f"in {pet_name}'s plan today.{Style.RESET_ALL}"
    )


def format_recurrence_event(task, next_task) -> str:
    """Return a formatted line describing a completed task and its next occurrence.

    Args:
        task:      The task that was just completed.
        next_task: The next-occurrence Task returned by mark_complete(), or None.

    Returns:
        A multi-line formatted string showing the completion and the follow-up.
    """
    done_line = (
        f"  {Fore.GREEN}✓{Style.RESET_ALL}  Completed "
        f"{Fore.WHITE}{Style.BRIGHT}'{task.name}'{Style.RESET_ALL}"
        f"  (was due {task.due_date}, recurrence={task.recurrence})"
    )
    if next_task:
        next_line = (
            f"     {Fore.CYAN}↻  Next: '{next_task.name}' due "
            f"{Style.BRIGHT}{next_task.due_date}{Style.RESET_ALL}"
        )
        return f"{done_line}\n{next_line}"
    return done_line
