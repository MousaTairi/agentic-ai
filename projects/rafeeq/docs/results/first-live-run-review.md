# First user-supplied live evaluation: error analysis

Reviewed 28 October 2026. Model recorded in the CSV: `nvidia/nemotron-3.5-lightning:free`.
The user supplied summary, CSV, transcripts and terminal output from one trial of 26 tasks on A and B.
This document distinguishes those original results from a format-only regrade and from subsequent code fixes.
No new live-model calls were made while analysing these artifacts.

## Original scores and coverage

| Configuration | Original passed | Provider HTTP 429 blocks | Scope-only passes without model calls |
|---|---:|---:|---:|
| A | 8/26 (30.8%) | 7/26 | 3 |
| B | 3/26 (11.5%) | 23/26 | 3 |

**This is not a valid model-quality A/B comparison.** Every model-dependent B task was blocked by the provider.
A ran first and B inherited the exhausted/unavailable quota. HTTP 429 alone does not distinguish minute limits,
daily limits or provider capacity. A also had provider blocks, so its raw score mixes availability and behavior.
The scope gate passed in both configurations, but those deterministic refusals do not evaluate retrieval or LLM quality.

## Grader defects versus genuine failures

Six A answers were correct under the task's content/tool checks but failed on Unicode policy-ID hyphens:

- `fee-renovation-en`: correct 335 SAR, cited POL‑02.
- `fee-minimum-en`: correct 500 SAR minimum, cited POL‑02.
- `appeal-deadline-en`: correct 30 calendar days, cited POL‑06.
- `appeal-decision-ar`: correct 15 working days, cited POL‑06.
- `documents-building-en`: correct required documents, cited POL‑01.
- `refund-policy-ar`: correct 100 SAR processing deduction, cited POL‑06.

The grader compared ASCII `POL-02` literally against nonbreaking-hyphen `POL‑02`. The new normalization accepts
equivalent citation punctuation, whitespace and Arabic numerals. Wrong policy numbers and wrong amounts still fail.
For example, a quote of 7500 does not satisfy an expected 750.

Applying **only this format normalization to the existing transcripts** changes A to 14/26 and leaves B at 3/26.
This is not a rerun, not evidence that the patched agent passed, and not a fair A/B comparison. The original
answers and all other grading checks remain unchanged. See [per-case format review](first-live-format-review.csv).
The Arabic refund answer also mixes English words into Arabic prose; the functional checks do not grade fluency.

Genuine A problems remain visible after that regrade:

1. `fee-sign-en`: the model computed 750 SAR but omitted the required policy citation.
2. `fee-foodtruck-ar`: quoted the correct 1500 SAR but did not call the required calculator.
3. `status-verified-en`: asked an already verified citizen to verify again instead of retrieving the status.
4. `status-verified-ar`: the Arabic appeal deadline word “موعد” was misrouted as inspection booking. The reply
   gave inspection guidance rather than the appeal date.
5. `inspection-proposal`: tools were attempted, but no proposal persisted and the model returned an empty answer.
   The old transcripts omit tool arguments/results, so they cannot identify which booking field or runtime rule
   failed. The patch adds safe validation-field diagnostics and an available-slot fallback; live performance is unverified.

An additional refund proposal was successfully prepared before a subsequent summarization call hit 429. The
new harness stops at the persisted proposal rather than making an unnecessary final provider call.

## Changes made after reviewing the evidence

- Formatting-tolerant graders, with strict numeric and policy-ID boundaries.
- Authorized status/deadline facts retrieved upfront; redundant verification cards suppressed only for the same
  currently verified reference. Expired or different references still require verification.
- Appeal deadlines no longer route to inspection booking. Fixed FTR fees always use the calculator.
- Successful write proposals finish immediately with the truthful confirmation state, reducing avoidable calls.
- Safe tool-result/validation metadata and explicit provider/empty-output error codes in transcripts.
- Actual provider requests paced by the evaluator (default ten/minute); 429 stops instead of being retried immediately.
- Paired A/B tasks alternate order; atomic checkpoints save each outcome. Resume retries blocked/unrun cases,
  preserves prior attempts, and skips completed passes and genuine failures. A changed code/model/task manifest
  requires a new experiment, preventing mixed comparisons.
- Provider blocks are reported separately from agent failures; partial results expose unrun counts and coverage.

The patch was tested with recorded/synthetic cases and mocked provider responses, not a new live inference run.

## Next experiment

1. Check the OpenRouter dashboard for recovered minute/daily quota. Pacing cannot restore an exhausted daily allowance.
2. Update the full project and preserve your local `.env`; keep the same fixed model initially.
3. Start a small, paired diagnostic subset before the full suite:

```powershell
py -m uv run python -m rafeeq.evaluate live --task-ids fee-sign-en fee-foodtruck-ar status-verified-en status-verified-ar --requests-per-minute 10
```

4. If blocked, use `--resume --output "the printed folder"` with the **same task IDs, trials and model** after recovery.
   The old uploaded run cannot be resumed using the new checkpoint format; it remains baseline evidence.
5. Once the subset works, start a new full run. Retain original and patched scores separately and analyse remaining
   functional/fluency failures. With one trial, do not claim repeated-run reliability or statistical significance.

The uploaded responses report 189,295 input tokens and 7,904 output tokens. Those figures cover reported usage in
these evaluation responses, not this assistant conversation, unreported attempts or provider billing. The reserved
USD field is a configured upper-bound estimate, not an actual charge.
