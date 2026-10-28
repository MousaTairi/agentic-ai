# Tests and results

The latest Linux validation on 28 October 2026 passed **65 pytest cases** and Ruff with Python 3.12.14.
The offline attack test and retrieval benchmark also passed their checks. Live-model testing is still
limited by provider quota.

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
extracting the complete ZIP resolved it. The native Windows full test suite has not yet been recorded.
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

After the fixes, the four-task Windows diagnostic stopped at `fee-sign-en` on A with
`blocked_provider` / `rate_limit`. The other seven cases did not run. The configured key was present;
a rate limit does not establish an invalid key. Earlier cloud checks had separate missing-key and 401
failures, which do not describe the credentials used by the Windows run.

The updated runner alternates A/B order, paces requests, and saves progress after each outcome.
`analysis.md` reports coverage and grader categories without raw prompts or replies. It is a starting
point for reviewing the local transcripts, not an automatic explanation of why a task failed.
A changed model, source, task set, trial count, or request rate starts a new experiment.

## Security check

`rafeeq.redteam` uses an isolated unguarded fixture to show the private lookup an attack requests.
The guarded lookup blocks that access, and the unavailable email tool is rejected. This tests the
backend boundary directly. Live-model resistance to retrieved-document injection has not yet been measured.
See the [security note](security.md).

## Next checks

- Finish the small live diagnostic after quota recovery, then run all 26 tasks on both configurations.
- Inspect Arabic fluency, citations, tool behavior, privacy, and confirmation states in the real responses.
- Run the live privacy/approval attacks and retain reviewed synthetic-only results.
- Record a native Windows full-suite result and check the remote CI runs.
- Complete a full accessibility audit; the existing browser checks cover only selected layouts and interactions.
