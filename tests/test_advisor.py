import tempfile
from pathlib import Path

import pytest

from care_advisor.advisor import CareAdvisor
from care_advisor import logging_store
from pawpal_system import Owner, Pet, Task, Scheduler


class StubClient:
    """Records the prompts it was called with and returns a canned answer."""

    def __init__(self, answer: str):
        self.answer = answer
        self.calls = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        return self.answer


@pytest.fixture(autouse=True)
def isolated_log(monkeypatch):
    """Point the log at a temp file so tests don't pollute the real log."""
    tmp_log = Path(tempfile.mktemp())
    monkeypatch.setattr(logging_store, "LOG_FILE", tmp_log)
    yield tmp_log


def test_answer_question_includes_retrieved_ids_in_prompt():
    stub = StubClient(answer="Brush weekly. [S1]")
    advisor = CareAdvisor(client=stub)

    response = advisor.answer_question("How often should I brush my long-haired cat?")

    assert stub.calls, "expected the client to be called"
    system_prompt = stub.calls[0]["system"]
    for chunk in response.retrieved:
        assert chunk.chunk.id in system_prompt


def test_answer_question_marks_grounded_when_citation_valid():
    stub = StubClient(answer="Placeholder")

    def fake_complete(system, user):
        sources_section = system.split("Sources:")[1]
        first_id = sources_section.split("[")[1].split("]")[0]
        return f"Brush regularly. [{first_id}]"

    stub.complete = fake_complete
    advisor = CareAdvisor(client=stub)

    response = advisor.answer_question("How often should I brush my dog?")

    assert response.grounding.grounded is True
    assert response.confidence > 0


def test_answer_question_flags_fabricated_citation():
    stub = StubClient(answer="Brush weekly. [S99999]")
    advisor = CareAdvisor(client=stub)

    response = advisor.answer_question("How often should I brush my dog?")

    assert response.grounding.grounded is False
    assert "S99999" in response.grounding.invalid_ids


def test_answer_question_refuses_emergency_without_calling_model():
    stub = StubClient(answer="should never be returned")
    advisor = CareAdvisor(client=stub)

    response = advisor.answer_question("My dog is bleeding badly, help!")

    assert response.refused is True
    assert stub.calls == []


def test_answer_question_logs_interaction(isolated_log):
    stub = StubClient(answer="Brush weekly. [S1]")
    advisor = CareAdvisor(client=stub)

    advisor.answer_question("How often should I brush my dog?")

    records = logging_store.read_recent(5, log_path=isolated_log)
    assert len(records) == 1
    assert records[0]["kind"] == "question"


def test_review_plan_builds_description_from_scheduler():
    stub = StubClient(answer="Looks fine. [S1]")
    advisor = CareAdvisor(client=stub)

    owner = Owner(name="Alex", available_hours=3)
    pet = Pet(name="Biscuit", species="Dog", breed="Golden Retriever", age=4)
    owner.add_pet(pet)
    pet.add_task(Task(name="Morning walk", type="walk", duration=30, priority="high", preferred_time="08:00"))
    scheduler = Scheduler(owner=owner, pet=pet)
    scheduler.generate_plan()

    response = advisor.review_plan(scheduler)

    assert stub.calls
    assert "Morning walk" in stub.calls[0]["user"]
    assert "Biscuit" in stub.calls[0]["user"]


def test_review_plan_handles_empty_plan_without_calling_model():
    stub = StubClient(answer="should never be returned")
    advisor = CareAdvisor(client=stub)

    owner = Owner(name="Alex", available_hours=3)
    pet = Pet(name="Biscuit", species="Dog", breed="Golden Retriever", age=4)
    owner.add_pet(pet)
    scheduler = Scheduler(owner=owner, pet=pet)
    scheduler.generate_plan()

    response = advisor.review_plan(scheduler)

    assert stub.calls == []
    assert response.confidence == 0


def test_ensure_client_raises_clear_error_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    advisor = CareAdvisor()

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        advisor.answer_question("How often should I brush my dog?")
