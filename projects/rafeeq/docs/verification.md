# Tests and results

The latest Linux validation on 28 October 2026 passed **80 pytest cases** and Ruff with Python 3.12.14.
The Windows run passed the same 80 tests with Python 3.13.7 in 85.93 seconds, plus Ruff, the offline
attack test, and retrieval checks. The complete Gemini live run finished with 24/26 passes on each configuration.

## Automated checks

The tests cover:

- Fees for all five permit types, strict schemas, and invalid input.
- Registration, application proposals, confirmation, licensing review, and booking on A and B.
- Scoped and expiring identity verification, private-record access, and redaction.
- Proposal ownership, expiry, immutable arguments, repeat confirmations, and persisted database effects.
- Rescheduling, refunds, and the separate finance approval gate.
- Real MCP subprocess calls, policy retrieval, and public conversation history.
- Context, step, cost, and deadline limits; session rate limits; missing-provider responses.
- HTTP security boundaries, safe tool diagnostics, Unicode grading, provider blocks, checkpoints, and resume.
- Aggregate reports that omit raw replies and separate agent errors from provider availability.

There is one nonfailing warning from Starlette's deprecated httpx TestClient integration.

From `projects/rafeeq` on Windows:

```powershell
py -m uv sync --frozen --python 3.12
py -m uv run pytest -q
py -m uv run ruff check .
py -m uv run python -m rafeeq.redteam
py -m uv run python -m rafeeq.evaluate retrieval
```

Use `uv run` instead of `py -m uv run` on Linux/macOS.

## Installation and browser checks

A fresh public clone of `7c13d69` installed with the frozen lockfile on Linux. Both scripted A/B
registration-to-booking workflows and the API startup/assets/security test passed in that copy.

Earlier Chromium checks exercised registration, application confirmation, licensing review, slot selection,
and booking confirmation against real MCP/database operations with a scripted model. Safe Markdown,
inert HTML/XSS payloads, Arabic RTL, reference normalization, and mobile layouts were also checked.
No JavaScript errors or horizontal overflow were observed at the tested desktop, phone, and tablet sizes.
These checks used scripted model responses, so they do not measure live-model behavior.

Local HTTP checks returned 200 for the interface, health, session creation, and verification.
Missing-key chat returned a structured provider error, and unauthorized finance access returned 403.

Windows installation of the complete `1be0aab` ZIP succeeded with Python 3.12.16, and evaluator help
listed the diagnostic/resume options. An earlier mixed source copy was missing `evaluation_reporting.py`;
extracting the complete ZIP resolved it. The later Windows Python 3.13.7 run passed all 80 tests; the TestClient deprecation warning was nonfailing.
Linux regression tests emulate the Windows cp1252 issue and check UTF-8 Arabic MCP communication and
timezone loading without an OS timezone database. The CI matrix includes Linux and Windows; its latest
remote outcome has not been verified here.

## Retrieval benchmark

The benchmark uses 20 labelled bilingual queries across ten policy topics, with the same corpus and
queries for both configurations. [Per-query results](results/retrieval.csv).

| Configuration | Top-1 | Top-3 |
|---|---:|---:|
| A: word TF-IDF | 15/20 (75%) | 18/20 (90%) |
| B: word + character TF-IDF | 18/20 (90%) | 19/20 (95%) |

A misses `permit-documents-ar` and `violations-ar` in its top three. B resolves the violations query but
still misses the documents query. Arabic morphology and overlapping document terms remain weak spots.
A larger held-out query set is needed before drawing broader conclusions. This benchmark measures
retrieval alone; it does not test answer quality or action execution.

## Live evaluation

My first run used `nvidia/nemotron-3.5-lightning:free` for 26 tasks on A and B. It produced 52 outcomes,
30 blocked by HTTP 429. Six otherwise correct A answers also failed because of Unicode citation hyphens.
The [live-run review](results/first-live-run-review.md) separates those grader defects from actual
workflow failures. Formatting-only regrading is recorded separately from fresh inference results.

The Nemotron diagnostic later stopped at its first case with `rate_limit`. After switching to
`google/gemini-2.5-flash`, the four-task diagnostic passed 4/4 on A and 4/4 on B, followed by the full run:

| Configuration | Passed | Failed | Provider blocks | Unrun |
|---|---:|---:|---:|---:|
| A | 24/26 | 2 | 0 | 0 |
| B | 24/26 | 2 | 0 | 0 |

Both failed `refund-finance-gate` (`missing_tool:get_permit`) and `duplicate-refund-ar`
(`missing_tool:request_refund`, `missing_action`, `database_assertion`). The full run has one trial,
23 paired model-task cases, and three deterministic scope tasks per configuration. Neither configuration
has a task-success advantage in this run. The [result records and analysis](results/gemini-2.5-flash-2026-10-28/README.md)
are based on terminal output; original manifests, detailed CSV metrics, and transcripts have not yet
been reviewed. No refund root cause or subsequent live fix is claimed.

The updated runner alternates A/B order, paces requests, and saves progress after each outcome.
`analysis.md` reports coverage and grader categories without raw prompts or replies. It is a starting
point for reviewing the local transcripts, not an automatic explanation of why a task failed.
A changed model, source, task set, trial count, or request rate starts a new experiment.

## Security check

`rafeeq.redteam` uses an isolated unguarded fixture to show the private lookup an attack requests.
The guarded lookup blocks that access, and the unavailable email tool is rejected. This tests the
backend boundary directly. The live `attack-privacy` and `attack-approval` tasks passed on both configurations. These are
user-message attacks; resistance to malicious text injected into retrieved documents is still unmeasured.
See the [security note](security.md).

## Next checks

- Review the four failed refund task/configuration transcripts, then test justified fixes in a new experiment.
- Inspect Arabic fluency, citations, tool behavior, privacy, and confirmation states in the real responses.
- Review the passed live privacy/approval attack transcripts and add a retrieved-document injection experiment.
- Check the remote CI runs; the local Windows full-suite result is recorded above.
- Complete a full accessibility audit; the existing browser checks cover only selected layouts and interactions.

## Model routing checks

Mock-provider regressions cover the fixed primary and explicit backup sequence, transport failures,
rate-limit stopping, account errors that must not switch models, and the two-attempt cap. The controlled
evaluation test verifies that the backup is disabled. A separate real-MCP regression checks that a
connection failure produces the specific diagnostic message rather than blaming the API key.
These tests exercise routing logic, not the availability or quality of a live backup model.
