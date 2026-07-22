"""Append-only interaction log for reliability/auditability.

Every Care Advisor call (question or plan review) gets one JSON line here,
independent of whether it passed or failed the guardrails -- refusals and
ungrounded answers are logged too, since those are exactly the cases an
audit needs to see.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "interactions.jsonl"


def append_interaction(record: dict, log_path: Optional[Path] = None) -> dict:
    """Append `record` as one JSON line, stamped with a UTC timestamp.

    Returns the stamped record (with 'timestamp' added) for convenience.
    """
    path = Path(log_path) if log_path else LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    stamped = {"timestamp": datetime.now(timezone.utc).isoformat(), **record}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(stamped) + "\n")
    return stamped


def read_recent(n: int = 20, log_path: Optional[Path] = None) -> list:
    """Return the last `n` logged interactions, newest first.

    Returns an empty list if the log doesn't exist yet -- callers shouldn't
    need to special-case a fresh install with no interactions logged.
    """
    path = Path(log_path) if log_path else LOG_FILE
    if not path.exists():
        return []

    with path.open(encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]

    records = [json.loads(line) for line in lines[-n:]]
    records.reverse()
    return records
