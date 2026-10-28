# Course requirements

I built Rafeeq for SDAIA Academy's [Agentic AI Systems Engineering course](https://github.com/SDAIAAcademy/agentic-ai),
using the “Rafeeq in production” track. This page maps the [course requirements](https://github.com/SDAIAAcademy/agentic-ai/tree/main/labs/capstone)
to the implementation. The [README](../README.md) explains the project itself.

| Requirement | Implementation | Status |
|---|---|---|
| Multi-step agent with 3+ tools, including MCP | Native tool-calling loop; policy search, fee calculation, and inspection availability over real MCP | Local workflow tests pass; Latest Gemini live run completed 26/26 on each configuration; local integration tests cover end-to-end registration/booking |
| Context file | `AGENTS.md`, loaded as UTF-8 on each turn | Implemented |
| Memory or retrieval | Bilingual policy retrieval, bounded public conversation history, and persisted citizen/application state | Tested locally |
| Compaction or budget rule | 12-message history limit and context, tool-result, and output caps | Tested locally |
| Human approval for a write | Stored application, booking, rescheduling, and refund proposals; explicit citizen confirmation | Ownership, expiry, idempotence, and database effects tested |
| Step and cost budgets | Eight model steps, four tool calls per response, estimated provider-cost reservation | Tested; pricing assumptions still depend on the selected model |
| 15+ tasks on two configurations | 26 automatically graded live-agent tasks; A uses word retrieval, B adds character n-grams | Post-fix Gemini run: 26/26 on A and B, zero blocks/unrun; one trial per task |
| Error analysis | Retrieval misses and first live-run analysis, including grading defects and actual workflow failures | Baseline and complete Gemini results in `docs/results/`; refund causes reviewed, fixes tested locally and live, final original summary/CSV published with manual-review findings |
| Security note with an attack and defence | Trifecta analysis, private-record scope, separate roles, immutable proposals, and offline attack simulation | Offline defence and both live user-message attack tasks pass; retrieved-document injection testing is pending |

## Assessment areas

| Area | Weight | Project material |
|---|---:|---|
| Working system | 25% | Chat/API, example workflows, MCP tools, and database tests |
| Context and harness | 25% | Context specification, retrieval, memory, schemas, permissions, and budgets |
| Evaluation and error analysis | 20% | Task suite, A/B runner, checkpoint reports, and results analysis |
| Security, governance, and operability | 20% | Security note, attack simulation, audit events, and role separation |
| Presentation and reproducibility | 10% | README, setup instructions, lockfile, architecture, and verification notes |

I chose one native Chat Completions loop because the workflow fits a small set of tools and explicit
approval states. Multiple agents, LangGraph, all three API formats, and a dynamic skill loader are
course topics, but are not separate minimum requirements for this track. The repository documents the
features actually implemented rather than treating the whole course stack as a dependency list.

## Final evidence

The [post-fix results](results/gemini-2.5-flash-2026-10-29/README.md) meet the 15-task/two-configuration
requirement with 26 tasks on each side. The earlier failed run, error analysis, regression tests, targeted
refund diagnostic, and complete post-fix run show the evaluation/fix cycle. Both configurations tie on
this single trial. Manual language and response-quality findings are recorded even though the automatic
graders pass all cases.

All five stated technical minimums have implementation and test evidence. This remains a synthetic
course project: a retrieved-document injection experiment, repeated-run reliability, production identity,
retention controls, and a full accessibility audit are outside the completed validation. The README
serves as the project's written presentation; this mapping does not assign an official grade.
