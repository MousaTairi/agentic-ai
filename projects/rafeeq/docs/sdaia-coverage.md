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
| 15+ tasks, two configurations, automatic graders | 26 live-agent JSONL tasks, A/B retrieval configurations; grader checks tools, content, scope, secure cards and actual database changes | Live provider execution is **blocked by missing API key in the cloud workspace**. Run both configurations with a pinned model and export reviewed results |
| Error analysis | Recorded 20-query retrieval comparison and failure categories; live runner emits per-task CSVs and failure summaries | Retrieval A top-3 18/20; B 19/20. These are not agent success scores. Live agent failure analysis remains outstanding |
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
| Evaluation and error analysis | 20% | 26-task live runner, two controlled configurations, offline retrieval CSV and workflow tests. Actual live scores are still required |
| Security, governance, operability | 20% | Structural audit events, no secret logging, immutable approvals, reviewer/finance separation, offline attacks and browser rendering checks; synthetic-only/PDPL limitations documented |
| Presentation and reproducibility | 10% | README, `.env.example`, lockfile, architecture and presentation outline; final slides, clean-clone rehearsal and demo recording remain required |

## Run locally on Windows

From `projects/rafeeq`, use `py -m uv sync --frozen`, then
`py -m uv run uvicorn rafeeq.api:create_app --factory --host 127.0.0.1 --port 8000`.
Keep your OpenRouter key only in ignored `.env`. For live comparisons pin `RAFEEQ_MODEL` to an available
tool-calling model, then run `py -m uv run python -m rafeeq.evaluate live --trials 1`.
Do not report scripted-model results or free-router model mixtures as a controlled model-quality comparison.
