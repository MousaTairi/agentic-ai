# Rafeeq · رفيق

A bilingual permit assistant for citizens of fictional Madar Municipal Services.

**SDAIA capstone track:** 1 — Rafeeq in production. This is an educational service using synthetic records;
it does not issue real permits, send emails, or transfer money. Team: fill in your name(s) before submission.

![Rafeeq citizen portal](docs/interface-desktop.png)

## Run

From a clone of **this entire course fork**, with Python 3.12 and [uv](https://docs.astral.sh/uv/):

```bash
cd projects/rafeeq
uv sync --frozen
cp .env.example .env  # first run only; preserve an existing .env
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
update the project, run `python -m uv sync --frozen`, and restart the server. Preserve your existing `.env`.

For the finance-officer demo, generate a separate random token locally, place it in `RAFEEQ_OFFICER_TOKEN`,
restart the server, and enter it in the footer's officer panel. It is not the AI provider key.
This panel demonstrates a separate role; a shared token is not production staff authentication.

The default `openrouter/free` routes requests dynamically. For final evaluation pin `RAFEEQ_MODEL` to an
available tool-calling model so A and B use the same model. Do not claim a model's quality until measured.
No API key is supplied with the project. The interface and local tools work without one, but chat needs a real key.

## Try the demo

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

The live suite has **20 tasks**, run on **two configurations**, using the same configured model.
Each task gets a fresh synthetic database. Graders assert tool calls, policy citations, content, privacy,
approval states, and actual database effects. Some tasks give confirmation through the evaluator's simulated
human; the model never gets that permission. Result CSVs, transcripts and root-cause summaries go to an ignored,
timestamped `evals/results/` directory. A failing task exits nonzero. A missing key or unpinned free router exits 2.
These graders are starting checks: manually review Arabic fluency, citation support and misleading claims as well.

The separate 20-query offline retrieval benchmark is **not** an end-to-end agent score. Do not substitute its
results for the capstone's live-model evaluation. Export reviewed synthetic-only result CSVs and error analysis
into `docs/results/` before final submission. Never publish raw transcripts containing secrets or real PII.

## Submission checklist

- Live AI demo with 3+ tools, MCP and a visible approval; record a backup video.
- Real-model A/B evaluation CSVs, failure analysis and pinned model/date; repeat key cases if budget allows.
- Security attack and defence evidence, privacy/PDPL discussion and limitations.
- README, architecture, environment template, lockfile and slides; rehearse the eight-minute talk.
- Test installation and demo from a clean clone. See [presentation outline](docs/presentation.md).

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
