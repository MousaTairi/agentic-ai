# Verification evidence

Validated in the cloud workspace on 28 October 2026 with Python 3.12.14. This is current-instance validation,
not proof of publication, GitHub Actions execution, or restoration in a new cloud task.

## Completed checks

- Fresh public-clone check of commit `7c13d69`: `uv sync --frozen --python 3.12` installed successfully in a new
  directory and environment. Three critical tests passed: both A/B scripted registration-to-booking workflows
  with real MCP/database operations, plus API startup/assets/security checks. The published clone contains
  `intake.py`, `scope.py`, `chat-forms.js` and `markdown.js`. This checks reproducibility on Linux, not native Windows
  or a live AI provider.

- Frozen dependency installation with `uv sync --frozen`; dependency versions recorded in `uv.lock`.
- 49 pytest cases covering all five fee types, schema rejection, privacy boundaries, scoped/expiring identity,
  approval ownership, immutable proposals, replay/idempotence, database persistence, rescheduling, separate finance
  approval, real MCP subprocess round trips, public follow-up context, cost/step/context/deadline controls,
  rate limits, missing-provider handling, and HTTP security boundaries.
- Agent review adds unrelated-request rejection before model calls; mandatory MCP grounding; registration,
  application proposal/confirmation, human review and booking workflows on both A/B configurations; normalized
  lowercase/Arabic references; verified profile recovery; expired identity privacy; accurate proposal-state
  replies; provider-auth failure messages; event attendance rules and exemption boundaries.
- Chromium exercised inline registration → application draft → citizen confirmation → separate licensing review
  → real slot search/selection → booking confirmation in an isolated database. It also checked safe bold/list/table/
  line-break rendering, inert HTML/XSS payloads, lowercase/Arabic numeral references, and mobile RTL without
  JavaScript errors. That browser run used a **scripted model fixture with real MCP/database operations**;
  it did not measure live model quality or claim provider connectivity.
- Windows regression coverage reproduces the reported cp1252 decoding failure, then verifies explicit UTF-8
  prompt/policy loading and an Arabic scripted-model turn through the real MCP subprocess. Timezone loading
  is also tested without an OS timezone database. These checks ran on Linux with the Windows encoding emulated;
  native Windows execution is covered by the new CI matrix, whose outcome has not been verified here.
- Ruff checks and JavaScript syntax check (`node --check src/rafeeq/web/app.js`).
- Redesigned interface checked in Chromium at desktop, 390px phone, 768px tablet and 1024px widths,
  including Arabic RTL, service prompt shortcuts, real form verification, clearing sensitive form fields,
  and explicit preview mode. No JavaScript errors, failed asset requests or horizontal overflow were observed.
  Relative CSS/JS routes and content types are covered by the API boundary test. Direct `file:` navigation is
  blocked by the managed browser policy, so preview behavior was checked using `?preview=1` on the service.
- Actual local HTTP smoke: HTML 200, health 200, session 200, verification 200, missing-key chat returns a
  structured `provider_error`, and unauthorized officer access returns 403. No AI answer was produced.
- Offline attack/defence demonstration (`python -m rafeeq.redteam`): isolated unguarded fixture read discloses
  a status; guarded lookup and unavailable egress tool are blocked. This simulates tool calls, not model reasoning.

One nonfailing upstream warning remains: Starlette deprecates its current httpx TestClient integration.
The integration tests executed and passed; this warning does not disable them.

## Measured offline A/B retrieval

20 manually labelled bilingual queries, ten policy topics, identical corpus and queries for A and B.
See [per-query CSV](results/retrieval.csv).

| Configuration | Mechanism | Top-1 | Top-3 |
|---|---|---:|---:|
| A | Word TF-IDF | 15/20 (75%) | 18/20 (90%) |
| B | Word + character TF-IDF | 18/20 (90%) | 19/20 (95%) |

**Error analysis:** A misses the expected policy in its top three for `permit-documents-ar` and `violations-ar`.
B resolves the violations query but still misses `permit-documents-ar`. Arabic morphology and overlapping
document vocabulary remain a retrieval weakness. This small hand-labelled sample does not establish statistical
significance or broad robustness. Next compare Arabic normalization/segmentation on a held-out query set;
do not tune the reported benchmark and report it as an independent result.

These are **retrieval results only**, not live-agent task success rates. The model, approval workflows, and bilingual
answer correctness are not evaluated by this retrieval benchmark.

## Outstanding before capstone submission

1. Set `OPENROUTER_API_KEY` securely in ignored `.env` or environment settings and restart the backend.
   Network settings must allow `openrouter.ai`; that requirement is saved in the cloud configuration draft.
2. Pin `RAFEEQ_MODEL` to an available tool-calling model and verify the pricing assumptions in `.env`.
3. Execute `uv run python -m rafeeq.evaluate live --trials 1` (26 agent tasks × two configurations).
   Earlier attempts exited 2 because a key was absent; the fresh-clone attempt stopped because the model was
   still the unpinned free router. A subsequent read-only authentication check using the current cloud binding
   returned HTTP 401. That does not establish whether the user's separate local key works. **Zero live-model
   tasks have run.** Configure a usable credential and a fixed tool-calling model before collecting results.
4. Review real A/B transcripts, export synthetic-only CSVs, write end-to-end failure analysis, and repeat important
   action/privacy cases if the provider budget permits. The free router is deliberately rejected for controlled evals.
5. Execute the live prompt-injection experiment and record a bilingual live demo plus a backup video.
6. Complete an accessibility audit, a native Windows rehearsal, and verify the new CI workflow on GitHub.
   Fresh-clone installation and critical API/MCP checks on Linux passed as recorded above.
   Desktop/mobile/RTL browser rendering was visually inspected; a full accessibility audit remains outstanding.
7. Add team names and prepare final slides using the presentation outline.

The environment draft saves installation/start instructions and the OpenRouter secret/destination requirement;
saving does not inject a key, apply network changes, publish a snapshot, or push the code to GitHub.
