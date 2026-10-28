# Documentation guide

The [README](../README.md) is the starting point for Rafeeq: what it does, how to run it, example
workflows, design choices, and results so far.

The other documents go into more detail:

- [Architecture](architecture.md): model calls, MCP, data flow, SQLite state, and approval transitions.
- [Security](security.md): private-data access, prompt injection, confirmations, and deployment risks.
- [Tests and results](verification.md): checks that have run, retrieval scores, and remaining validation.
- [Gemini A/B results](results/gemini-2.5-flash-2026-10-28/README.md): complete run, per-task outcomes, and refund failures.
- [Earlier Nemotron evaluation](results/first-live-run-review.md): quota blocks, grader errors, and workflow failures.
- [Course requirements](sdaia-coverage.md): how the project relates to the SDAIA course.

Live evaluation output stays in `evals/results/`, which is ignored by Git. Reviewed synthetic-only CSVs
and analysis belong in `docs/results/`. Raw transcripts, checkpoints, local databases, and API keys stay local.
