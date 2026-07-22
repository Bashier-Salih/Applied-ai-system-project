# PawPal+ AI Care Advisor

**Applied AI System Final Project** — a retrieval-augmented, guardrail-checked AI advisor
built on top of a deterministic pet-care scheduler.

## Original project

This extends **PawPal+** (Module 2 project — [`ai110-module2show-pawpal-starter`](https://github.com/Bashier-Salih/ai110-module2show-pawpal-starter)),
a Python/Streamlit app that helps a pet owner plan daily care tasks across multiple pets.
The original project's scope was entirely deterministic: it sorted tasks by priority and
preferred time, packed them into an owner's available time budget, detected scheduling
conflicts via interval-overlap arithmetic, and auto-requeued recurring tasks (daily/weekly)
via `timedelta` math — with a plain-text explanation of why each task landed where it did.
It contained no AI or LLM component.

---

## What this project does, and why it matters

PawPal+'s scheduler is good at the mechanical part of pet care planning — fitting tasks
into a time budget and catching double-bookings — but it has no way to know that a
Golden Retriever shouldn't be walked hard right after a big meal, or that a long-haired
cat needs daily brushing during shedding season. That kind of knowledge lives in
pet-care guidelines, not in scheduling arithmetic.

This project adds an AI layer, the **Care Advisor**, that closes that gap: it answers
free-text pet-care questions and reviews a generated schedule against a curated
knowledge base, flagging concerns the rule-based scheduler structurally cannot see —
while never being allowed to alter the schedule or override the rule-based conflict
checker itself. It matters because it demonstrates the pattern most real-world AI
features actually need: an LLM layered on top of a trusted deterministic system,
constrained so it can *advise* without being able to silently take over.

---

## Architecture Overview

Full diagram: [`diagrams/care_advisor_flow.mmd`](diagrams/care_advisor_flow.mmd).

```
Owner input (question, or "build today's plan")
        │
        ├──────────────────────────────┐
        ▼                               ▼
  Retriever                     Deterministic Scheduler
  (TF-IDF over knowledge/*.md)  (unchanged from Module 2)
        │                               │
        ▼                               │
  top-k cited chunks ──────────┐        │
                                ▼        │
                        Agent (Claude)  │
                        cites [S#] per  │
                        claim, using    │
                        plan context if │
                        reviewing ◄─────┘
                                │
                                ▼
                   Evaluator / Guardrails
             scope check → grounding check → confidence score
                                │
                ┌───────────────┼────────────────┐
                ▼               ▼                ▼
        scope refusal    ungrounded flag    grounded answer
        ("see a vet")    (low confidence)   + citations + score
                                │
                                ▼
                    Interaction log (logs/interactions.jsonl)
                                │
                                ▼
                          Owner reviews and decides
```

Two paths run side by side: the **deterministic Scheduler** (rule-based, always
authoritative — `detect_conflicts()` is untouched) and the **AI Care Advisor**
(advisory only). The UI always shows them as separate sections so the AI's opinion is
never confused with the scheduler's guarantees. Every AI response passes through the
evaluator before the owner ever sees it, and every call — including refusals — is
logged for later audit. Retrieval, the grounding checker, and the agent's prompt/parsing
are each covered by an offline pytest suite that runs with no network access
(`tests/test_retrieval.py`, `tests/test_guardrails.py`, `tests/test_advisor.py`).

---

## Setup Instructions

```bash
# 1. Clone and enter the project
git clone <this-repo-url>
cd Applied-ai-system-project

# 2. Create a virtual environment and install dependencies
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. (Optional) enable the AI Care Advisor
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...
export $(grep -v '^#' .env | xargs)   # or use direnv / python-dotenv

# 4. Run it
streamlit run app.py     # web UI
python main.py           # CLI demo
pytest                   # test suite
```

The scheduler (task entry, scheduling, conflict detection, filtering) works fully with
no API key. Without a key, the AI sections show a clear
`"ANTHROPIC_API_KEY is not set"` message instead of crashing — the rest of the app is
unaffected.

---

## Sample Interactions

These are real, unedited outputs from a live run against Claude (`python main.py`
equivalent), not hand-written examples.

**1. General care question**

> **Q:** How often should I brush a long-haired dog?
>
> **A:** Long-haired or double-coated dog breeds (like Golden Retrievers or Huskies)
> typically need brushing every day or every other day to prevent matting, especially
> during seasonal shedding [S23].
>
> `Confidence: 52/100 | Grounded: True | Sources: [S23, S42, S7, S1]`

**2. A question the knowledge base only partially answers**

> **Q:** Is it okay to give my dog medication at the same time as breakfast?
>
> **A:** It depends on the specific medication: many oral meds are absorbed better or
> cause less stomach upset when given with food, but some need to be given on an empty
> stomach, so the general rule is to avoid scheduling a medication in the exact same
> time slot as feeding unless a vet or the label specifically says to give it "with
> food" — instead, leave a 10-15 minute gap so it's clear which instruction is being
> followed [S27]. Since specifics vary by medication, check with your vet or the label
> for guidance on your dog's particular medication [S27].
>
> `Confidence: 50/100 | Grounded: True | Sources: [S27, S28, S44, S36]`

**3. Emergency question — guardrail refusal, not an AI-generated answer**

> **Q:** My dog is bleeding heavily and won't stop, what do I do?
>
> **A:** This looks like it may describe an active symptom or emergency. The Care
> Advisor is a scheduling and general-care helper, not a diagnostic tool — please
> contact your veterinarian or an emergency animal hospital instead of relying on this
> answer.
>
> `Refused: True` — the scope guardrail caught this before the model was ever called.

**4. AI Plan Review — catching what the rule-based scheduler can't**

Schedule: Biscuit (4-year-old Golden Retriever) has "Breakfast" at 08:00 (10 min) and
"Morning walk" at 08:10 (45 min). The rule-based `detect_conflicts()` reports **no
conflict** (the tasks don't overlap) — but:

> **AI review:** Feeding breakfast at 08:00 followed immediately by a 45-minute walk at
> 08:10 leaves only 10 minutes between eating and exercise. Golden Retrievers are a
> large breed, and large breeds are noted as more susceptible to bloat, which affects
> exercise-after-feeding guidance [S3]. This spacing may be worth reviewing.
>
> Beyond that, the sources don't indicate other concerns for a 4-year-old Golden
> Retriever's schedule — this life stage isn't senior [S17] or puppy [S34], so those
> adjustments don't apply here.
>
> `Confidence: 47/100 | Grounded: True`

---

## Design Decisions

- **Pure-Python TF-IDF instead of embeddings/vector DB.** The knowledge base is small
  (~12 curated docs, ~40 chunks) and needs to be fully inspectable and testable
  deterministically. A dict-based term-vector + cosine-similarity implementation
  (`care_advisor/retrieval.py`) needed zero extra dependencies beyond the stdlib and no
  external embedding calls, at the cost of missing semantic matches that don't share
  vocabulary with the query (e.g. it wouldn't connect "matting" to "grooming" unless
  both words appear near each other in a chunk). For this project's scale, that
  trade-off was worth it; a larger knowledge base would need real embeddings.
- **The AI never touches the deterministic core.** `Scheduler.detect_conflicts()`
  remains the single source of truth for "does this schedule have an overlap." The
  Care Advisor's plan review is additive and clearly separated in the UI — a design
  choice that trades away a "smarter" unified scheduler for a much easier trust story:
  nothing the AI outputs can silently change what gets scheduled.
- **Citations are mandatory, not optional.** Every prompt requires `[S#]` markers, and
  `check_grounding()` treats an uncited claim the same as a fabricated citation —
  ungrounded. This is stricter than most RAG demos (which often just show sources
  alongside an answer without verifying the model actually used them), and it does mean
  some genuinely correct answers get flagged if the model forgets a citation. That
  false-positive rate was an acceptable trade for catching real hallucinations.
- **A keyword-based scope classifier, not a model-based one.** `check_scope()` is a
  simple keyword list, not a second LLM call. It's cheaper, deterministic, and testable
  without mocking a model — but it's also blunt: it will refuse some non-emergency
  questions that happen to contain a trigger word (e.g. "is a little blood in stool
  normal after a treat?"). Given the cost asymmetry (a missed emergency is much worse
  than an over-cautious refusal), that trade-off was made deliberately.
- **Injectable client for testability.** `CareAdvisor(client=...)` accepts any object
  with a `.complete(system, user)` method, so the entire test suite
  (`test_advisor.py`, `test_guardrails.py`) runs against a stub client with zero network
  access. The real Streamlit/CLI entry points construct the actual Anthropic client
  lazily, only when a question is asked.

---

## Testing Summary

`pytest` — 29 tests, all passing, no network access required.

- **What worked:** Retrieval, grounding, and scope-refusal logic are all deterministic
  and straightforward to unit test in isolation (`test_retrieval.py`,
  `test_guardrails.py`). Injecting a stub client into `CareAdvisor` made it possible to
  test prompt construction, citation parsing, and logging (`test_advisor.py`) without
  ever calling the real API — this caught a real bug during development (see below)
  purely from test output, before any live API call was made.
- **What didn't work initially:** An early version of `test_advisor.py` grabbed the
  first `[S#]`-looking bracket out of the system prompt to build a "valid citation" test
  case — but the prompt's own instructions text contains an example citation
  (`"...exactly like [S3]."`) before the real sources list, so the test grabbed that
  instead of an actual retrieved chunk id, and failed. It wasn't a bug in the
  advisor — it was a test that made too strong an assumption about prompt structure.
  Fixed by anchoring the search to text after the literal `"Sources:"` marker.
- **What I learned:** Once live API calls were run (see Sample Interactions above), the
  confidence scores came back lower (47-52/100) than expected for answers that were, on
  inspection, correctly grounded and reasonable. That's because the retrieval component
  of the score (cosine similarity against a small TF-IDF vocabulary) rarely produces
  very high similarity values even for good matches — the scoring formula weighs
  retrieval quality and grounding roughly evenly, so a "good but not perfect" retrieval
  match caps the score around 50 even when the model's citation is completely valid.
  That's a calibration issue worth revisiting (e.g. reweighting toward grounding, which
  is the stronger trust signal) rather than a correctness bug, and is a good example of
  a metric that "worked" in the sense of running correctly, but needs tuning to be truly
  useful to an end user glancing at the number.

---

## Reflection

Building this made the gap between "the AI answered" and "the AI answered *and I can
verify it*" very concrete. It's easy to wire an LLM up to some retrieved text and call
it RAG; it's a different, harder problem to make the system reject its own output when
the citations don't check out, or to decide in advance what kinds of questions it
should refuse to touch at all. The most interesting design work wasn't the retrieval or
the prompt — it was deciding where the trust boundary goes (the deterministic scheduler
never gets touched) and what "grounded" actually has to mean to be worth anything
(every claim, not just "some sources are shown below"). That's a pattern I'd now expect
to reuse anywhere an LLM sits on top of a system whose correctness actually matters.

*The graded responsible-AI reflection — collaboration process, one helpful and one
flawed AI suggestion, and system limitations — is in [`model_card.md`](model_card.md).*

---

## 🗂 Project Structure

```
pawpal_system.py       # Original Module 2 scheduler: Task, Pet, Owner, Scheduler (unchanged)
formatting.py          # Original CLI formatting helpers (unchanged)
app.py                 # Streamlit UI: scheduler + AI Care Advisor sections
main.py                # CLI demo: scheduler features + AI Care Advisor demo

knowledge/              # Curated pet-care knowledge base (markdown, citation source)
care_advisor/
  retrieval.py          # Pure-Python TF-IDF DocStore
  guardrails.py         # Scope classifier, grounding checker, confidence scorer
  advisor.py            # CareAdvisor: retrieval -> Claude -> guardrails -> log
  logging_store.py      # Append-only logs/interactions.jsonl

tests/                  # pytest suite (scheduler + retrieval + guardrails + advisor)
diagrams/               # UML (uml_final.mmd/png) + care_advisor_flow.mmd (system diagram)
logs/                   # interactions.jsonl (created on first AI interaction)
```

## 📐 Original PawPal+ Scheduler Reference

The original Module 2 features — priority scheduling, chronological sorting, task
filtering, conflict detection, and recurring tasks — are unchanged. See
[`pawpal_system.py`](pawpal_system.py) for `Scheduler.prioritize_tasks()`,
`Scheduler.sort_by_time()`, `Owner.filter_tasks()`, `Scheduler.detect_conflicts()`, and
`Task.mark_complete()` / `Pet.complete_task()` for the full deterministic scheduling logic
this project builds on.
