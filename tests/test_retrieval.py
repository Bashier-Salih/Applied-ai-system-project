from care_advisor.retrieval import DocStore, tokenize


def test_tokenize_lowercases_and_drops_stopwords():
    tokens = tokenize("The Dog Needs Exercise, and Grooming.")
    assert "the" not in tokens
    assert "and" not in tokens
    assert "dog" in tokens
    assert "exercise" in tokens
    assert "grooming" in tokens


def test_retrieve_returns_relevant_grooming_chunk():
    store = DocStore()
    results = store.retrieve("how often should I brush a long haired dog", k=3)
    assert results, "expected at least one relevant chunk"
    assert results[0].chunk.source_file == "grooming_frequency.md"


def test_retrieve_returns_relevant_medication_chunk():
    store = DocStore()
    results = store.retrieve("can I give medication at the same time as feeding", k=3)
    assert results, "expected at least one relevant chunk"
    assert results[0].chunk.source_file == "medication_timing.md"


def test_retrieve_ranks_by_similarity_descending():
    store = DocStore()
    results = store.retrieve("puppy exercise and feeding schedule", k=5)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_excludes_zero_score_chunks():
    store = DocStore()
    results = store.retrieve("zzzznonsensequerywithnomatches", k=5)
    assert results == []


def test_get_by_id_roundtrip():
    store = DocStore()
    first = store.chunks[0]
    fetched = store.get_by_id(first.id)
    assert fetched == first


def test_get_by_id_unknown_returns_none():
    store = DocStore()
    assert store.get_by_id("S9999") is None


def test_chunk_ids_are_unique_and_sequential():
    store = DocStore()
    ids = [c.id for c in store.chunks]
    assert len(ids) == len(set(ids))
    assert ids == [f"S{i + 1}" for i in range(len(ids))]
