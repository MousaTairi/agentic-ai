# Course requirements

I built Rafeeq for SDAIA Academy's [Agentic AI Systems Engineering course](https://github.com/SDAIAAcademy/agentic-ai),
using the “Rafeeq in production” track. This page maps the [course requirements](https://github.com/SDAIAAcademy/agentic-ai/tree/main/labs/capstone)
to the implementation. The [README](../README.md) explains the project itself.

| Requirement | Implementation | Status |
|---|---|---|
| Multi-step agent with 3+ tools, including MCP | Native tool-calling loop; policy search, fee calculation, and inspection availability over real MCP | Local workflow tests pass; updated live-model evaluation is pending |
| Context file | `AGENTS.md`, loaded as UTF-8 on each turn | Implemented |
| Memory or retrieval | Bilingual policy retrieval, bounded public conversation history, and persisted citizen/application state | Tested locally |
| Compaction or budget rule | 12-message history limit and context, tool-result, and output caps | Tested locally |
| Human approval for a write | Stored application, booking, rescheduling, and refund proposals; explicit citizen confirmation | Ownership, expiry, idempotence, and database effects tested |
| Step and cost budgets | Eight model steps, four tool calls per response, estimated provider-cost reservation | Tested; pricing assumptions still depend on the selected model |
| 15+ tasks on two configurations | 26 automatically graded live-agent tasks; A uses word retrieval, B adds character n-grams | First run had 30 provider blocks; a complete post-fix run is pending |
| Error analysis | Retrieval misses and first live-run analysis, including grading defects and actual workflow failures | Published in `docs/results/`; updated results still needed |
| Security note with an attack and defence | Trifecta analysis, private-record scope, separate roles, immutable proposals, and offline attack simulation | Offline defence passes; live-model injection testing is pending |

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
