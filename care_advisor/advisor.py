"""CareAdvisor: retrieval-grounded Q&A and plan review on top of PawPal+.

The Anthropic client is injected rather than constructed inline, so tests
can pass a stub that returns canned text with zero network access. The
Streamlit/CLI entry points construct the real client lazily, only when a
question is actually asked, and surface a clear error if no API key is set.

DEMO NOTE: this is the "Agent" box in diagrams/care_advisor_flow.mmd, and
it's the orchestrator that ties the whole pipeline together. Follow
answer_question() below top to bottom to see the full flow: scope check ->
retrieve -> ask Claude -> grounding check -> confidence score -> log.
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

# Loads ANTHROPIC_API_KEY / PAWPAL_MODEL from a .env file in the project
# root into os.environ, if one exists. `streamlit run app.py` and
# `python main.py` don't read .env on their own, so without this, setting
# values in .env would silently have no effect unless the caller had
# manually exported them first. Never overrides a variable that's already
# set in the real environment (e.g. exported in the shell or set by CI).
load_dotenv()

from care_advisor.retrieval import DocStore, RetrievedChunk
from care_advisor.guardrails import (
    ScopeCheck,
    GroundingResult,
    check_scope,
    check_grounding,
    confidence_score,
    SCOPE_REFUSAL_MESSAGE,
)
from care_advisor.logging_store import append_interaction

DEFAULT_MODEL = "claude-sonnet-5"
NO_SOURCES_MESSAGE = (
    "I don't have enough information in my knowledge base to answer that "
    "confidently, so I'd rather not guess."
)

# This is the system prompt sent to Claude on every question/plan review.
# The three rules that matter most for the guardrails downstream: (1) only
# use the sources below, (2) cite every claim with [S#], (3) never diagnose.
# {sources} gets filled in with the actual retrieved chunks for this query.
SYSTEM_PROMPT_TEMPLATE = """You are the PawPal+ Care Advisor, a general pet-care assistant.

Rules:
- Answer ONLY using the numbered sources below. Do not use outside knowledge.
- Every factual claim you make must end with the matching citation marker, exactly like [S3].
- If the sources don't fully answer the question, say so plainly instead of guessing.
- Never diagnose a medical condition or judge whether a symptom is an emergency. If the question describes one, say to contact a veterinarian.
- Be concise: a few sentences, not an essay.

Sources:
{sources}
"""


def _format_sources(retrieved: list) -> str:
    """Turn retrieved chunks into the numbered "[S3] Title — Heading: text"
    block that gets dropped into the system prompt above."""
    lines = []
    for r in retrieved:
        c = r.chunk
        lines.append(f"[{c.id}] {c.doc_title} — {c.heading}: {c.text}")
    return "\n\n".join(lines)


class AnthropicClientAdapter:
    """Thin adapter so CareAdvisor only depends on a `.complete(system, user)` method.

    This indirection is what makes the advisor testable: tests inject a
    fake object with a `.complete()` method instead of this real one, so
    they never make a network call to Anthropic.
    """

    def __init__(self, sdk_client, model: str):
        self._client = sdk_client
        self._model = model

    def complete(self, system: str, user: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )


@dataclass(frozen=True)
class AdvisorResponse:
    """Everything the UI needs to render one Care Advisor answer: the raw
    text, which sources backed it, whether it passed the grounding
    guardrail, its 0-100 confidence score, and whether it was refused
    outright by the scope guardrail before Claude was even called.
    """
    query: str
    answer: str
    retrieved: list = field(default_factory=list)
    grounding: Optional[GroundingResult] = None
    confidence: int = 0
    refused: bool = False
    refusal_reason: Optional[str] = None


class CareAdvisor:
    def __init__(self, doc_store: Optional[DocStore] = None, client=None, model: Optional[str] = None):
        # doc_store defaults to a fresh DocStore (loads + indexes knowledge/*.md).
        # client defaults to None and is built lazily -- see _ensure_client().
        self.doc_store = doc_store or DocStore()
        self.client = client
        self.model = model or os.environ.get("PAWPAL_MODEL", DEFAULT_MODEL)

    def _ensure_client(self):
        """Build the real Anthropic client on first use, or reuse an
        injected one (tests always pass one, so this branch never runs
        during pytest)."""
        if self.client is not None:
            return self.client
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set -- the Care Advisor needs it to call "
                "Claude. Set the environment variable and try again."
            )
        import anthropic  # imported lazily so the package isn't required just to run tests

        self.client = AnthropicClientAdapter(anthropic.Anthropic(api_key=api_key), self.model)
        return self.client

    def _no_sources_response(self, query: str) -> AdvisorResponse:
        """Used when retrieval comes back empty -- we'd rather say "I don't
        know" than let the model answer with zero grounding available."""
        grounding = GroundingResult(grounded=False, reason="no relevant sources retrieved")
        response = AdvisorResponse(
            query=query, answer=NO_SOURCES_MESSAGE, retrieved=[],
            grounding=grounding, confidence=0,
        )
        self._log(kind="no_sources", query=query, response=response)
        return response

    def _refused_response(self, query: str, scope: ScopeCheck) -> AdvisorResponse:
        """Used when check_scope() flags the question -- note Claude is
        never called in this path at all."""
        response = AdvisorResponse(
            query=query, answer=SCOPE_REFUSAL_MESSAGE, retrieved=[],
            grounding=None, confidence=0, refused=True, refusal_reason=scope.reason,
        )
        self._log(kind="scope_refusal", query=query, response=response)
        return response

    def _log(self, kind: str, query: str, response: AdvisorResponse):
        """Every path through the advisor (refusal, no-sources, or a real
        answer) ends up here, so logs/interactions.jsonl has a complete
        audit trail -- not just the "successful" answers."""
        append_interaction({
            "kind": kind,
            "query": query,
            "answer": response.answer,
            "retrieved_ids": [r.chunk.id for r in response.retrieved],
            "retrieval_scores": [r.score for r in response.retrieved],
            "grounded": response.grounding.grounded if response.grounding else None,
            "confidence": response.confidence,
            "refused": response.refused,
        })

    def answer_question(self, question: str, k: int = 4) -> AdvisorResponse:
        """Full Q&A pipeline for a free-text pet-care question.

        Step by step: (1) scope guardrail, refuse emergencies immediately;
        (2) retrieve top-k relevant chunks; (3) bail out if nothing relevant
        was found; (4) build the citation-required prompt and call Claude;
        (5) grounding guardrail on the raw response; (6) confidence score;
        (7) log everything.
        """
        scope = check_scope(question)
        if not scope.in_scope:
            return self._refused_response(question, scope)

        retrieved = self.doc_store.retrieve(question, k=k)
        if not retrieved:
            return self._no_sources_response(question)

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(sources=_format_sources(retrieved))
        client = self._ensure_client()
        raw_answer = client.complete(system_prompt, question)

        retrieved_ids = [r.chunk.id for r in retrieved]
        grounding = check_grounding(raw_answer, retrieved_ids)
        confidence = confidence_score([r.score for r in retrieved], grounding)

        response = AdvisorResponse(
            query=question, answer=raw_answer, retrieved=retrieved,
            grounding=grounding, confidence=confidence,
        )
        self._log(kind="question", query=question, response=response)
        return response

    def review_plan(self, scheduler) -> AdvisorResponse:
        """Ask the advisor to flag care concerns in an already-generated plan.

        `scheduler` is a pawpal_system.Scheduler with generate_plan() already
        called. This never touches scheduler.detect_conflicts() or the plan
        itself -- it only reads the plan to build a review, which the UI
        shows in a clearly separate section from the rule-based conflicts.

        Same guardrail pipeline as answer_question() above, just with a
        different "query": instead of a user's question, the query is a
        text description of the pet + today's schedule, built from the
        deterministic Scheduler's own data.
        """
        plan = scheduler.generated_plan
        pet = scheduler.pet
        summary_label = f"{pet.name}'s schedule review"

        if not plan:
            return self._no_sources_response(summary_label)

        # Turn the Scheduler's plan into a plain-text description Claude can read.
        plan_lines = [
            f"- {t.scheduled_time} {t.name} ({t.type}, {t.duration} min, "
            f"priority={t.priority}, recurrence={t.recurrence or 'none'})"
            for t in plan
        ]
        plan_description = (
            f"{pet.name} is a {pet.age}-year-old {pet.breed} {pet.species.lower()}.\n"
            f"Today's schedule:\n" + "\n".join(plan_lines)
        )

        # Retrieve using the plan's task types + species (e.g. "walk feeding dog")
        # rather than a user-typed question, since there's no free-text query here.
        query_terms = " ".join({t.type for t in plan} | {pet.species.lower()})
        retrieved = self.doc_store.retrieve(
            f"{query_terms} schedule review care concerns", k=6
        )
        if not retrieved:
            return self._no_sources_response(summary_label)

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(sources=_format_sources(retrieved))
        user_prompt = (
            f"{plan_description}\n\n"
            "Review this schedule for any care concerns (timing, spacing, "
            "frequency, or life-stage fit). List only real concerns grounded "
            "in the sources, each with a citation. If there are none, say so."
        )

        client = self._ensure_client()
        raw_answer = client.complete(system_prompt, user_prompt)

        retrieved_ids = [r.chunk.id for r in retrieved]
        grounding = check_grounding(raw_answer, retrieved_ids)
        confidence = confidence_score([r.score for r in retrieved], grounding)

        response = AdvisorResponse(
            query=summary_label, answer=raw_answer, retrieved=retrieved,
            grounding=grounding, confidence=confidence,
        )
        self._log(kind="plan_review", query=summary_label, response=response)
        return response
