# Rafeeq · رفيق

A bilingual permit assistant for citizens of fictional Madar Municipal Services.

**SDAIA capstone track:** 1 — Rafeeq in production. This is an educational service using synthetic records;
it does not issue real permits, send emails, or transfer money.

**Submission format:** the instructor has specified a GitHub link, with this README serving as the presentation.
Separate slides and an oral presentation are not required for this submission.

![Rafeeq citizen portal](docs/interface-desktop.png)

## Project and assessment evidence

Rafeeq helps citizens understand five permit types (BLD, REN, SGN, FTR, EVT), register a synthetic profile,
prepare applications, check their own records, propose inspections, understand appeals and request refunds.
The problem is reliable bilingual service delivery: answers need policy evidence, calculated fees and actual
record state, while changes require consent. Appeals are guidance/drafting; Rafeeq cannot lodge or decide them.

| Assessment criterion | Evidence in this repository | Current limitation |
|---|---|---|
| Working system (25%) | [Citizen workflow below](#try-the-demo), API and real MCP tools; automated registration-to-booking tests | Post-fix live-model reliability remains unmeasured |
| Context/harness (25%) | [Context specification](AGENTS.md), [architecture](docs/architecture.md), retrieval, bounded memory, typed tools, permissions and budgets | Bounded history drops older public turns; no dynamic Agent Skills loader |
| Evaluation (20%) | [26 tasks](evals/tasks.jsonl), automatic content/tool/database graders, A/B retrieval configurations, [baseline error analysis](docs/results/first-live-run-review.md) | No complete post-fix live A/B comparison yet |
| Security/governance/operability (20%) | [Trifecta, attack and defence](docs/security.md), scoped private reads, confirmations, separate officer roles and audit events | Offline attack evidence is not a live-model injection result; synthetic demonstration only |
| README/reproducibility (10%) | This README, frozen lockfile, Windows commands, [verification evidence](docs/verification.md), Linux/Windows CI configuration | Native Windows installation/help confirmed by user; native Windows full test-suite result not supplied |

**Latest local checks:** 65 tests and Ruff passed on Linux, including real MCP/database workflows
and report/checkpoint regressions. The offline attack fixture was blocked by the guarded lookup and tool allowlist.
These checks do not measure live-model intelligence.

**Measured results:** the offline 20-query retrieval benchmark scores A 15/20 top-1 and 18/20 top-3;
B 18/20 top-1 and 19/20 top-3. A uses word TF-IDF; B adds character n-grams, holding the corpus constant.
These are retrieval scores, not end-to-end agent scores. The earlier live run scored A 8/26 and B 3/26,
with 30 provider blocks. A format-only regrade changes A to 14/26; it is not a fresh run.
The updated Windows diagnostic was stopped on its first case by `rate_limit`, leaving all eight diagnostic
outcomes either blocked or unrun. There is no valid model-quality winner from those live attempts.

The project deliberately uses one native tool-calling loop. MCP is the tool transport; SQLite holds durable
state; Python enforces permissions. Multiple agents, LangGraph and dynamic skill loading are not necessary
for the stated capstone minimum. A model proposes actions; only backend-authorized human decisions execute them.

## Run

**Windows / PowerShell (recommended for this submission):** open a terminal in `projects/rafeeq`
inside the complete repository, not the repository root. Preserve any existing `.env` and `runtime/`.

```powershell
py -m uv sync --frozen --python 3.12
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env securely: set OPENROUTER_API_KEY and RAFEEQ_MODEL.
# Current experiment model: nvidia/nemotron-3.5-lightning:free
py -m uv run python -m rafeeq.evaluate --help
py -m uv run uvicorn rafeeq.api:create_app --factory --host 127.0.0.1 --port 8000
```

The evaluator help must list `--task-ids`, `--requests-per-minute` and `--resume`.
If `rafeeq.evaluation_reporting` is missing, the source copy is incomplete: extract a full repository ZIP
into a new folder and copy your private `.env`/runtime there. Do not merge individual downloaded source files
or copy an old `.venv`. A ZIP must include `labs/prepare_data.py` and `labs/data/policies/` as well as this project.
Use the new folder in VS Code and reinstall with the frozen command above.

**Linux/macOS:**

From a clone of **this entire course fork**, with Python 3.12 and [uv](https://docs.astral.sh/uv/):

```bash
cd projects/rafeeq
uv sync --frozen
if [ ! -f .env ]; then cp .env.example .env; fi
# Edit .env locally: set OPENROUTER_API_KEY and choose RAFEEQ_MODEL.
uv run uvicorn rafeeq.api:create_app --factory --host 127.0.0.1 --port 8000
```

Open the local interface in your browser. The backend serves `src/rafeeq/web/index.html` with local CSS and
JavaScript assets; no Node build or external fonts are needed. Opening the HTML directly provides a styled
preview with language switching; chat and verification require the backend. Add `?preview=1` to the served
page to explore that preview mode explicitly. The API schema is at `/openapi.json`.
The application loads this project's `.env` automatically; already exported variables take precedence.
Never commit `.env`, paste keys into chat, or put keys into HTML. `.env.example` explains each supported setting.
Free-provider model names, availability and quotas change; verify them in your OpenRouter dashboard.

**Windows:** bilingual files and MCP communication explicitly use UTF-8. The `tzdata` dependency supplies the
Riyadh timezone when no system timezone database exists. If an older version shows a `'charmap' codec` error,
update the project, run `py -m uv sync --frozen --python 3.12`, and restart the server. Preserve your existing `.env`.

For the finance-officer demo, generate a separate random token locally, place it in `RAFEEQ_OFFICER_TOKEN`,
restart the server, and enter it in the footer's officer panel. It is not the AI provider key.
This panel demonstrates a separate role; a shared token is not production staff authentication.

The default `openrouter/free` routes requests dynamically. For final evaluation pin `RAFEEQ_MODEL` to an
available tool-calling model so A and B use the same model. Do not claim a model's quality until measured.
No API key is supplied with the project. The interface and local tools work without one, but chat needs a real key.

## Try the demo

For the full chat workflow, ask **“I want to apply for a food truck permit.”** Rafeeq retrieves policy evidence
and opens a secure registration card inside chat. Use synthetic details only; identity fields are not sent to AI.
Registration opens an inline application form. Select the type and district, enter fee inputs, and declare the
documents you have. These are **demo declarations, not file uploads**. Review the fee and missing documents,
then confirm the proposal. A synthetic application and simulated payment are recorded atomically.

Complete declarations produce `submitted`; missing declarations produce `needs_info`. Submission does not
approve a permit. For a new application to become eligible for inspection, a separate licensing officer must
take it into review. Configure `RAFEEQ_REVIEWER_TOKEN` in your local `.env`, restart, then use **Licensing reviewer
demo workspace** at the bottom of the page. Validate declarations and start review. This token must be separate
from the finance token; the reviewer endpoint cannot approve/reject permits. Under-review FTR/EVT may have
pre-approval inspections, while approved BLD/FTR have the inspections allowed by POL-05.

Ask **“Book an inspection.”** Verification can happen inside a secure chat card. Rafeeq reads the recorded district,
uses a default simulation date range, and retrieves actual slots. If a weak model only explains the process,
the harness provides a slot-selection card. Confirm the resulting proposal in chat to persist the booking.
Existing applicants can verify a reference to reconnect to their profile. No real account or money transfer is created.

Unrelated requests, including sorting code and weather, are rejected before model calls. Supported replies are
grounded by MCP policy retrieval. Markdown renders as safe DOM nodes; model HTML cannot execute. Lowercase
references, Unicode hyphens and Arabic numerals are normalized in the browser and backend.

1. Ask: “What is the fee for an illuminated 3 m² sign?” Expect a tool-computed 750 SAR and POL-02.
2. Verify synthetic applicant `FTR-30311`, last four ID digits `6654`, mobile `0532236654` using the form.
3. Ask: “Find inspection slots for FTR-30311 in Al-Rawdah on 4 November 2026 and propose 09:00.”
4. Confirm the action card. The booking is persisted only after this click. Repeated confirmation is idempotent.
5. Switch to Arabic and ask another policy question.
6. Demonstrate the finance gate with `SGN-40220`, `0093`, `0540410093`: rejected-fee refund is 2,700 SAR;
   citizen confirmation queues it for a separate officer decision. No real money moves.

**Time:** municipal records use the course's fixed **1 November 2026, 09:00 Asia/Riyadh** simulation clock,
explicitly labelled in the UI and prompt. The current actual date is supplied separately to the model.
Generated inspection availability ends after 15 working days. Do not book against the actual calendar.

## Design across the ladder

| Rung | Choice | Reason |
|---|---|---|
| Prompt | `AGENTS.md` system specification and validated tool schemas | Explicit scope, language and evidence requirements |
| Context | Bilingual policy retrieval; bounded public conversation history | Retrieve current source facts and support public follow-ups |
| Harness | Application-scoped verification, write proposals, separate officer gate | Enforce permissions in code |
| Loop | One native tool-calling agent, max 8 model steps and 4 calls per response | Small, inspectable control surface |
| Graph | Persisted pending → awaiting_officer/completed/rejected states | Durable approvals without unnecessary multi-agent complexity |

Private application replies are omitted from retained conversation history. Future turns must retrieve records
again through authorization. Public conversation pairs are retained up to 12 messages; tool outputs are never
stored in conversational memory. The model receives only minimized verified record fields, not full IDs or mobiles.
Verification expires after 15 minutes, proposals after 10 minutes, sessions after 24 hours. All data is synthetic.

Configuration A uses word TF-IDF retrieval; B adds character n-gram TF-IDF with fixed 55/45 weighting.
This lexical hybrid helps with Arabic word variants; it is not embedding-based semantic search.

Budgets check input size, up to 8 model steps, tool-result size, output tokens and a 60-second turn deadline.
The cost guard conservatively reserves both possible HTTP attempts using configured pricing upper bounds and
UTF-8 byte counts. It is an estimate, not a provider billing cap; verify pricing and set a provider-side spend cap.
Rate limits are per session (15 requests/minute), not production IP/account abuse prevention.

See [architecture](docs/architecture.md) for data flow and state, [security](docs/security.md) for boundaries,
and [verification](docs/verification.md) for measured results and unresolved checks.

## Tools

| Tool | Transport | Effect | Approval |
|---|---|---|---|
| `search_policies` | MCP stdio | Read public policies | None |
| `compute_fee` | MCP stdio | Calculate public fee | None |
| `list_inspection_slots` | MCP stdio | Read public availability | None |
| `start_registration`, `start_verification`, `start_application` | In-process | Open secure inline forms | Citizen submits form |
| `my_applications` | In-process | Minimized owned references/status | Current identity verification |
| `submit_application` | In-process | Propose application + simulated payment | Citizen confirmation |
| `get_permit` | In-process | Minimized private read | Verified application scope |
| `book_inspection` | In-process | Propose booking | Citizen confirmation |
| `reschedule_inspection` | In-process | Propose reschedule | Citizen confirmation |
| `request_refund` | In-process | Propose refund | Citizen; also officer above 1,000 SAR |

Run the standalone read-only MCP server with `uv run python -m rafeeq.mcp_server`.
It speaks protocol messages on stdio; connect with an MCP client rather than typing into it.
Private records and writes are deliberately absent from this MCP server.

## API

All mutation endpoints require `X-Rafeeq-Client: 1`. Browser requests must be same-origin. Start a session first;
the server sets an opaque HttpOnly, SameSite=Strict cookie. HTTPS also enables Secure cookies.

| Method/path | Purpose |
|---|---|
| `GET /healthz` | Service status and whether an AI key is configured, never its value |
| `POST /api/session` | Start or resume a session |
| `DELETE /api/session` | Remove session memory/verification and cancel unconfirmed actions |
| `POST /api/verify` | `{permit_id, last4, mobile}`; never sent to AI provider |
| `POST /api/register` | Synthetic profile fields + explicit consent; never sent to AI provider |
| `GET /api/me` | Current citizen context, with application details hidden after verification expires |
| `GET /api/application-options` | Supported document declarations and districts |
| `POST /api/application-draft` | Prepare validated application proposal without submitting it |
| `POST /api/inspection-proposal` | Prepare a selected-slot proposal without booking it |
| `GET /api/reviewer/applications` | New application queue; separate reviewer token required |
| `POST /api/reviewer/begin-review` | Human reviewer starts review; no permit approval |
| `POST /api/chat` | `{message}` → reply, tools, action cards, stop reason, usage and trace ID |
| `GET /api/actions` | Current session's actions |
| `POST /api/actions/{id}/decision` | `{approve: true/false}` on immutable stored arguments |
| `GET /api/officer/actions` | Finance queue, requires `X-Officer-Token` |
| `POST /api/officer/actions/{id}/decision` | Separate officer decision |

The service is intended to run with **one worker**. Writes use SQLite transactions; approval decisions
revalidate eligibility and availability at execution time. Runtime records survive restarts. No auto-confirm route
is exposed to the model. Errors use JSON envelopes; tool errors do not reveal provider bodies or credentials.

## Validate and evaluate

```bash
uv run pytest -q
uv run ruff check .
uv run python -m rafeeq.evaluate retrieval
uv run python -m rafeeq.redteam
uv run python -m rafeeq.evaluate live --trials 1
# Use --trials 3 for repeated-run reliability if your API budget permits.
```

The live suite has **26 tasks**, run on **two configurations**, using the same configured model.
Each task gets a fresh synthetic database. Graders assert tool calls, policy citations, content, privacy,
approval states, and actual database effects. Some tasks give confirmation through the evaluator's simulated
human; the model never gets that permission. Result CSVs, transcripts and root-cause summaries go to an ignored,
timestamped `evals/results/` directory. Each saved outcome also refreshes `analysis.md`, an aggregate
coverage/error report that excludes raw prompts and replies. Its grader categories require manual root-cause review. A failing task exits nonzero. A missing key or unpinned free router exits 2.
These graders are starting checks: manually review Arabic fluency, citation support and misleading claims as well.

The separate 20-query offline retrieval benchmark is **not** an end-to-end agent score. Do not substitute its
results for the capstone's live-model evaluation. Export reviewed synthetic-only result CSVs and error analysis
into `docs/results/` before final submission. Never publish raw transcripts containing secrets or real PII.

The evaluator now alternates paired A/B tasks and paces actual provider requests at ten/minute by default.
Use `--requests-per-minute` to select a rate within your provider's current allowance; pacing does not restore
an exhausted daily quota. A provider error stops the run, writes an atomic checkpoint and reports the case as
`blocked_provider`, not a pile of missing-tool/content failures. Results also show unrun counts and comparison coverage.

For a diagnostic subset on Windows:

```powershell
py -m uv run python -m rafeeq.evaluate live --task-ids fee-sign-en fee-foodtruck-ar status-verified-en status-verified-ar --requests-per-minute 10
```

After quota/authentication recovers, resume using the printed results directory and identical task IDs, trials,
model and request rate:

```powershell
py -m uv run python -m rafeeq.evaluate live --resume --output "evals/results/YOUR_RUN_FOLDER" --task-ids fee-sign-en fee-foodtruck-ar status-verified-en status-verified-ar --requests-per-minute 10
```

Completed passes and genuine agent failures are preserved; only blocked/unrun cases are retried. Earlier blocked
attempts remain in `checkpoint.json`. A changed source/model/task manifest requires a new experiment, so an old
result folder from before checkpoints were introduced cannot be resumed. `manifest.json` records the model, code/
task fingerprints and non-secret run settings. A reported comparison is complete only when all cases ran without
provider blocks. Provider failures are not evidence that one retrieval configuration is worse.

See [the first submitted live-run analysis](docs/results/first-live-run-review.md) for raw scores, six Unicode
citation grading errors, real workflow failures and the HTTP 429 coverage problem. The format-only regrade is
labelled separately from new model results; patched agent performance still needs a fresh live run.

## GitHub-only submission checklist

The instructor's GitHub-only submission instructions take precedence over the upstream course's slides/talk
outline. This README is the presentation. The technical evaluation and security requirements still apply.

- Read the [requirement mapping](docs/sdaia-coverage.md), architecture and security note linked above.
- Run the local checks below; retain the real results rather than an estimated project score.
- Complete the four-task diagnostic, resolve actual failures, then run all 26 tasks on A/B with the same pinned model.
- Review `analysis.md`, `summary.json`, `agent-results.csv` and local transcripts. Add observed causes and fixes;
  do not count provider blocks as agent failures or describe partial runs as completed comparisons.
- Publish reviewed synthetic-only evaluation CSVs, aggregate report and written root-cause analysis under
  `docs/results/`. Never commit `.env`, runtime databases, raw transcripts, or checkpoint files.
- Include live privacy/approval attack evidence after provider access recovers. The offline defence is already documented.

Windows checks and full evaluation (from `projects/rafeeq`, after the diagnostic):

```powershell
py -m uv run ruff check .
py -m uv run pytest -q
py -m uv run python -m rafeeq.redteam
py -m uv run python -m rafeeq.evaluate retrieval
$env:RAFEEQ_MODEL = "nvidia/nemotron-3.5-lightning:free"
py -m uv run python -m rafeeq.evaluate live --trials 1 --requests-per-minute 10
```

A model/source change starts a new experiment; do not resume an older checkpoint after updating source.
A 429 does not establish an invalid API key. Check current OpenRouter quota before retrying; pacing cannot
restore an exhausted allowance. Do not launch the full evaluation while the small diagnostic remains blocked.
See the [submission guide](docs/presentation.md) for the README evidence-review order.

## Limitations

This is not a production municipal system: no real identity provider, staff SSO, payment rail, live calendar,
distributed rate limiter or secrets vault is integrated. Last-four-plus-mobile is a course simulation, not
strong authentication. Restarted sessions retain only deliberately minimized context.
Withdrawn-application refunds are routed to an officer because course records cannot prove withdrawal stage.
Appeals are guidance/drafting only. Repeat inspections for later construction stages need officer handling.
Full production deployment needs independent security review, data retention controls and monitored provider access.

## Attribution

Built on [SDAIAAcademy/agentic-ai](https://github.com/SDAIAAcademy/agentic-ai), specifically the Madar synthetic
data generator, bilingual policies, capstone starter concepts and API examples. Course files are preserved.
This project imports the standard-library data generator and reads policies from the existing checkout;
it does not download or run a local LLM. See the upstream repository for course materials and reuse terms.
