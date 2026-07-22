from care_advisor.guardrails import (
    check_scope,
    check_grounding,
    confidence_score,
    extract_citations,
)


def test_check_scope_flags_active_bleeding():
    result = check_scope("My dog is bleeding a lot from a cut, what do I do?")
    assert result.in_scope is False


def test_check_scope_flags_breathing_difficulty():
    result = check_scope("My cat is having difficulty breathing")
    assert result.in_scope is False


def test_check_scope_allows_normal_care_question():
    result = check_scope("How often should I brush my Golden Retriever?")
    assert result.in_scope is True


def test_extract_citations_dedupes_and_preserves_order():
    text = "Per [S3] and [S1], also see [S3] again."
    assert extract_citations(text) == ["S3", "S1"]


def test_extract_citations_empty_when_no_markers():
    assert extract_citations("No sources here.") == []


def test_check_grounding_accepts_valid_citation():
    result = check_grounding("Brush weekly per [S4].", retrieved_ids=["S4", "S7"])
    assert result.grounded is True
    assert result.invalid_ids == []


def test_check_grounding_rejects_fabricated_citation():
    result = check_grounding("Per [S99], do this.", retrieved_ids=["S4", "S7"])
    assert result.grounded is False
    assert "S99" in result.invalid_ids


def test_check_grounding_rejects_missing_citation():
    result = check_grounding("Just brush your dog weekly.", retrieved_ids=["S4"])
    assert result.grounded is False
    assert result.cited_ids == []


def test_confidence_score_high_when_grounded_and_similar():
    grounding = check_grounding("Per [S1].", retrieved_ids=["S1"])
    score = confidence_score([0.9, 0.8], grounding)
    assert score >= 80


def test_confidence_score_low_when_ungrounded():
    grounding = check_grounding("Per [S99].", retrieved_ids=["S1"])
    score = confidence_score([0.9, 0.8], grounding)
    assert score <= 60


def test_confidence_score_zero_with_no_retrieval_and_no_grounding():
    grounding = check_grounding("No citations.", retrieved_ids=[])
    score = confidence_score([], grounding)
    assert score == 0
