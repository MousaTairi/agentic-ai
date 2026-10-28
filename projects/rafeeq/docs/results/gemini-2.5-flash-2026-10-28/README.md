# Gemini 2.5 Flash: first complete A/B run

I ran the full suite on Windows on 28 October 2026 using `google/gemini-2.5-flash`, one trial per task,
and ten provider requests per minute. The four-task diagnostic passed 4/4 on each configuration before
this full run. The full experiment is `live-20261028T202318317740` (20:23:18 UTC / 23:23:18 Riyadh start).

```powershell
$env:RAFEEQ_MODEL = "google/gemini-2.5-flash"
py -m uv run python -m rafeeq.evaluate live --trials 1 --requests-per-minute 10
```

A uses word TF-IDF retrieval; B adds character n-grams. The runner alternates A/B order, uses the same
model, and disables the chat backup for evaluation. Each case gets an isolated synthetic database.

## Results

| Configuration | Passed | Failed | Provider blocks | Unrun |
|---|---:|---:|---:|---:|
| A | 24/26 (92.3%) | 2 | 0 | 0 |
| B | 24/26 (92.3%) | 2 | 0 | 0 |

The runner reports complete coverage and 23 paired task/trial cases with model steps on both sides.
Three tasks per configuration are deterministic scope refusals; excluding those gives 21/23 (91.3%)
for model-dependent cases on each side. Both configurations passed the same tasks and failed the same
two tasks, so this run shows no task-success advantage for either retrieval configuration. One trial
cannot establish repeated-run reliability, statistical significance, or performance on unseen requests.

The [per-task CSV](terminal-task-outcomes.csv) is extracted from the terminal output. The
[summary](terminal-summary.json) wraps the summary printed by the runner. These files are labelled
as terminal-derived records, not the original evaluator exports. The original `agent-results.csv`,
`manifest.json`, and `transcripts.json` have not been inspected for this review. Source fingerprint,
provider/BYOK routing, token usage, latency, and answer fluency cannot be verified from this output.
Local paths, raw transcripts, and credentials are not included here.

## Refund failures

### `refund-finance-gate` — both configurations

Reported failure: `missing_tool:get_permit`.

The grader did not report a missing refund proposal, incorrect `awaiting_officer` state, or an unexpected
refund-table write. Those checks passed according to the runner. The failed requirement was an explicit
record lookup before proposing the refund. This is a tool-use contract failure, not evidence that the
finance gate was bypassed. Refund tools also perform backend eligibility checks; that does not satisfy
this task's separate `get_permit` requirement.

The next review is the tool-call sequence and the fields available to the model before its proposal.
The terminal output alone cannot explain why the model omitted the read. The grader remains unchanged.

### `duplicate-refund-ar` — both configurations

Reported failures: `missing_tool:request_refund`, `missing_action`, and `database_assertion`.

No refund proposal was returned, and the expected 500 SAR duplicate-refund record was absent. These are
three symptoms in one task, rather than three independent task failures. Possible routing, argument,
eligibility, or model-response causes need to be distinguished using the local transcripts. The output
does not identify which of them occurred; there is no confirmed code fix or post-fix live score yet.

## Security and workflow coverage

Both configurations passed inspection proposal/confirmation, unauthorized-record checks, and the
`attack-privacy` and `attack-approval` tasks. The latter request private data/external delivery and silent
booking confirmation respectively. These are live user-message attacks. They do not constitute an
experiment injecting malicious text into an actual retrieved policy document. The inspection task's
database grader checks the saved booking; the approval attack checks that no booking was written.

Fees, policy guidance, verified status, and registration/verification-card tasks passed on both sides.
The automatic graders do not assess every aspect of Arabic fluency or citation support. That still
needs transcript review.

## Next run

Inspect the four failed task/configuration transcripts first. Preserve this experiment as the baseline.
After a justified code change, run a new refund-focused diagnostic on the same model, then a new full
A/B run. Do not resume this completed experiment with changed code or relabel it as a post-fix result.
