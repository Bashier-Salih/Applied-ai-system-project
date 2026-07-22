"""Trust layer for the Care Advisor: scope refusal, grounding checks, and
a confidence score. These are what let the AI's output be treated as
advisory rather than authoritative -- see pawpal_system.Scheduler for the
deterministic, always-trusted scheduling logic this layer never overrides.
"""

import re
from dataclasses import dataclass, field
from typing import Iterable

_CITATION_RE = re.compile(r"\[S(\d+)\]")

# Keyword-based emergency/diagnostic classifier. Deliberately simple and
# over-inclusive: false positives (redirecting a borderline question to a
# vet) are much cheaper than false negatives (the advisor answering a real
# emergency instead of a vet).
_EMERGENCY_KEYWORDS = (
    "bleeding", "blood", "vomiting blood", "can't breathe", "cannot breathe",
    "difficulty breathing", "not breathing", "collapse", "collapsed",
    "unresponsive", "poison", "poisoned", "seizure", "seizing", "convulsing",
    "bloated", "distended", "distended abdomen", "can't urinate",
    "cannot urinate", "hit by a car", "hit by car", "dying", "emergency",
    "unconscious",
)

SCOPE_REFUSAL_MESSAGE = (
    "This looks like it may describe an active symptom or emergency. "
    "The Care Advisor is a scheduling and general-care helper, not a "
    "diagnostic tool -- please contact your veterinarian or an emergency "
    "animal hospital instead of relying on this answer."
)


@dataclass(frozen=True)
class ScopeCheck:
    in_scope: bool
    reason: str


def check_scope(question: str) -> ScopeCheck:
    """Flag questions describing an active symptom/emergency for vet redirect."""
    lowered = question.lower()
    for keyword in _EMERGENCY_KEYWORDS:
        if keyword in lowered:
            return ScopeCheck(
                in_scope=False,
                reason=f"question matched emergency keyword '{keyword}'",
            )
    return ScopeCheck(in_scope=True, reason="no emergency keywords detected")


def extract_citations(text: str) -> list:
    """Return the ordered, de-duplicated list of '[S#]' ids cited in text."""
    seen = []
    for match in _CITATION_RE.finditer(text):
        chunk_id = f"S{match.group(1)}"
        if chunk_id not in seen:
            seen.append(chunk_id)
    return seen


@dataclass(frozen=True)
class GroundingResult:
    grounded: bool
    cited_ids: list = field(default_factory=list)
    invalid_ids: list = field(default_factory=list)
    reason: str = ""


def check_grounding(answer_text: str, retrieved_ids: Iterable) -> GroundingResult:
    """Verify every citation in `answer_text` matches an actually-retrieved id.

    Grounded requires: at least one citation is present, AND every cited id
    is one of `retrieved_ids`. A response with zero citations, or one citing
    an id that was never retrieved (a fabricated/hallucinated source), is
    flagged as ungrounded.
    """
    retrieved_id_set = set(retrieved_ids)
    cited_ids = extract_citations(answer_text)
    invalid_ids = [cid for cid in cited_ids if cid not in retrieved_id_set]

    if not cited_ids:
        return GroundingResult(
            grounded=False, cited_ids=[], invalid_ids=[],
            reason="answer contains no source citations",
        )
    if invalid_ids:
        return GroundingResult(
            grounded=False, cited_ids=cited_ids, invalid_ids=invalid_ids,
            reason=f"answer cites unretrieved source(s): {', '.join(invalid_ids)}",
        )
    return GroundingResult(
        grounded=True, cited_ids=cited_ids, invalid_ids=[],
        reason="all citations verified against retrieved sources",
    )


def confidence_score(retrieval_scores: Iterable, grounding: GroundingResult) -> int:
    """Combine retrieval similarity + grounding pass/fail into a 0-100 score.

    Retrieval quality contributes up to 60 points (how well the retrieved
    chunks actually matched the query); grounding contributes the other 40
    (whether the model's citations check out). An ungrounded answer is
    capped well below a grounded one regardless of retrieval quality, since
    a fabricated citation is a bigger trust problem than a weak match.
    """
    scores = list(retrieval_scores)
    avg_score = sum(scores) / len(scores) if scores else 0.0
    retrieval_component = min(max(avg_score, 0.0), 1.0) * 60
    grounding_component = 40 if grounding.grounded else 0
    return round(min(100, max(0, retrieval_component + grounding_component)))
