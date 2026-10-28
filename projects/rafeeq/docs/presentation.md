# GitHub submission guide

The instructor has specified that only the GitHub link is submitted and the project README is the
presentation. Separate slides and an oral presentation are not required. The upstream course's timed
presentation outline is therefore not the submission format for this project.

The assessor can review the project in this order:

1. [README](../README.md): problem, five permit types, evidence table, setup and citizen workflow.
2. [Architecture](architecture.md) and [context specification](../AGENTS.md): model/tool boundaries,
   retrieval, bounded memory, durable approvals, budgets and scope decisions.
3. [Verification](verification.md): executed checks and explicit limits of that evidence.
4. [Baseline live-run analysis](results/first-live-run-review.md): availability blocks versus actual failures
   versus grader formatting defects. Updated full live results remain outstanding.
5. [Security note](security.md): lethal trifecta, offline attack/defence, privacy and residual risks.
6. [Coverage](sdaia-coverage.md): requirement-by-requirement implementation and remaining work.

Before final submission, complete the post-fix paired live evaluation after quota recovery. Review and
publish synthetic-only CSVs, the generated aggregate `analysis.md` and a manual root-cause analysis in
`docs/results/`. Keep provider blocks, agent failures, unrun cases and scripted fixtures distinct.
No invented scores, raw private transcripts, API keys or runtime databases belong in the submission.
