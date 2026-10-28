# SDAIA capstone coverage — Track 1, Rafeeq in production

This maps the implementation to the course's minimum requirements and rubric. It does not claim that an
unexecuted live-model evaluation, native Windows CI job, production deployment, or presentation is complete.

## Minimum requirements

| Requirement | Implementation | Evidence / outstanding work |
|---|---|---|
| Multi-step agent, 3+ tools, one over MCP | Native tool-calling loop; three real MCP tools plus profile/application/verification/booking/refund tools | Scripted A/B workflow tests exercise policy retrieval → record lookup → slot search → booking proposal; real MCP and SQLite, no simulated tool results |
| Context file | `AGENTS.md` system specification | Loaded explicitly as UTF-8 on every turn |
| Memory or retrieval | Mandatory bilingual MCP retrieval; bounded task history; persisted citizen/application state | Follow-up, scope, privacy and Windows regression tests |
| Compaction or budget rule | 12-message history, context/result/output caps | Context/step/cost/deadline tests |
| Human approval on a write | Immutable booking, refund and application proposals; citizen confirmation | Database remains unchanged before confirmation; ownership, expiry, replays and false-completion tests |
| Step and cost budgets | Max eight model calls, four tool calls per model response, conservative price reservation | Cost guard and step-limit tests; configured prices must match the selected provider |
| 15+ tasks, two configurations, automatic graders | 26 live-agent JSONL tasks, paired A/B configurations; automatic graders, request pacing, checkpoints and resume | User supplied 52 live-task outcomes with a fixed model. Thirty hit provider HTTP 429, so the run is not a valid A/B quality comparison. A complete post-fix run is still required |
| Error analysis | Recorded retrieval comparison plus analysis of the submitted live transcripts | First live run separates six Unicode-citation false failures, genuine workflow errors and provider blocks; see `results/first-live-run-review.md`. Format-only regrading is not a new inference result |
| Security note, trifecta, attack and defence | `security.md`; separate roles, scoped reads, secure inline identity, no egress tools, safe Markdown | Offline red-team tool-call simulation and browser XSS check pass. Live-model injection susceptibility remains unmeasured |

## The actual citizen workflow

1. Ask to apply in Arabic or English. Rafeeq retrieves policy evidence and opens an inline registration card.
2. Submit synthetic identity/profile fields directly to the local service. They are not model tool arguments.
3. Complete an application form and review the computed fee and missing document declarations.
4. Confirm: create the application reference and simulated payment atomically. Repeated confirmation is idempotent.
5. A separate licensing reviewer validates declarations and starts review; the model cannot change this state.
6. Request an inspection. Verification uses a secure inline card if needed. District comes from the authorized record.
7. Search real slots using defaults or user-specified dates. A slot-selection fallback prevents tool-free tutorials
   from becoming a dead end. Prepare a proposal and obtain explicit citizen confirmation before booking.

The demo does not upload documents, verify a real identity, charge money or approve a permit. Document checkboxes
are declarations. Missing declarations produce `needs_info`; complete declarations produce `submitted`. FTR/EVT
under review may have pre-approval inspections. Reviewer and finance roles use separate credentials.

## Rubric

| Criterion | Weight | Prepared evidence |
|---|---:|---|
| Working system and live demo | 25% | API, bilingual chat, real MCP/database, in-chat intake and confirmation. Rehearse with the actual configured model and record a backup |
| Context and harness engineering | 25% | Mandatory grounding, safe task memory, strict schemas, scope gate, role gates, persisted proposals, budgets |
| Evaluation and error analysis | 20% | First 52-outcome live run and explicit failure analysis available. Pacing/stop/resume prevent misleading quota-driven comparisons; complete post-fix paired results are still required |
| Security, governance, operability | 20% | Structural audit events, no secret logging, immutable approvals, reviewer/finance separation, offline attacks and browser rendering checks; synthetic-only/PDPL limitations documented |
| Presentation and reproducibility | 10% | README, `.env.example`, lockfile, architecture and presentation outline. Fresh public-clone installation and three critical API/MCP workflow checks passed on Linux; final slides, Windows rehearsal and live-demo recording remain required |

## Course topics versus capstone requirements

The learning outcomes describe the whole course. The stated capstone minimum does not require every listed
library, every API shape, multiple agents or LangGraph. This implementation uses a native Chat Completions loop
with OpenRouter, MCP, Pydantic, FastAPI and SQLite. It has persisted human-gated workflow states and structural
audit events grouped by trace ID. It does not claim Responses/Messages adapters, an SDK harness, A2A, a LangGraph
implementation or OpenTelemetry span export. Explain these scope decisions in the presentation; additional
instructor-specific requirements would need separate implementation and validation.

## Run locally on Windows

From `projects/rafeeq`, use `py -m uv sync --frozen`, then
`py -m uv run uvicorn rafeeq.api:create_app --factory --host 127.0.0.1 --port 8000`.
Keep your OpenRouter key only in ignored `.env`. For live comparisons pin `RAFEEQ_MODEL` to an available
tool-calling model, then run `py -m uv run python -m rafeeq.evaluate live --trials 1`.
Do not report scripted-model results or free-router model mixtures as a controlled model-quality comparison.
