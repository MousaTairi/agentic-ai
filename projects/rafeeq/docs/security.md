# Security note

## Lethal trifecta

| Leg | Where it exists | Controls |
|---|---|---|
| Private data | Synthetic applicant and permit tables | Scoped verification before any private lookup; minimized returned fields |
| Untrusted input | Chat and retrieved policies/tool results | Data-only prompt rule, strict argument schemas, no arbitrary execution |
| External communication | HTTPS request to OpenRouter | Fixed backend endpoint; no email, shell, HTTP-fetch or arbitrary egress tools |

Authorized minimized permit fields can still go to the model provider. This does not eliminate all three legs.
Only synthetic records are permitted for this capstone. Do not send real personal data until appropriate data
processing approval, provider region/retention review and institutional policy review are complete.

## Attack and defence evidence

Attack text in the live evaluation task `attack-privacy` impersonates a system message, disables identity checks,
and requests another applicant's information and external delivery. `attack-approval` asks for silent auto-confirmation.

The offline test `test_injected_tool_access_is_blocked_in_code` directly simulates the tool calls an injected model
might request. A scoped private read fails without verification and `send_email` is rejected because it is absent
from the allowlist. The MCP server advertises only three public read tools. Additional tests prove the model cannot
alter action arguments at confirmation and cannot perform writes merely by proposing them.

These are **deterministic harness tests**, not proof that a live model resisted a retrieved-document injection.
For the final submission, run both attack tasks on the real provider and capture redacted evidence. To show a
before/after comparison, demonstrate an explicitly isolated unguarded fixture lookup, then the guarded API lookup;
never add a switch that disables production permissions or weaken configuration A's security.
Run `uv run python -m rafeeq.redteam` for an isolated offline before/after demonstration: an unguarded synthetic
fixture lookup exposes status, while the authorized tool blocks the same request, and rejects the egress tool.
No application permission toggle is introduced. The actual live-model before/after attack experiment remains
outstanding until an API key is configured.

## Additional controls

- Unrelated coding/general requests are rejected before provider calls, including after an existing permit conversation.
- Registration and identity verification are secure cards within chat. Identity/profile values go directly to local
  endpoints, not LLM messages. Application documents are synthetic declarations; no real files or payments are processed.
- Application submission requires an immutable citizen-confirmed proposal. A separate licensing-reviewer role starts
  review, while the finance role handles high-value refunds. Neither role is an AI tool or a permit approval endpoint.
- Agent replies cannot claim a proposed write completed: the harness reports its persisted pending state instead.
- Markdown uses DOM nodes only. Bold, lists, tables, citations and line breaks render without executing model HTML.

- Separate citizen confirmation and finance-officer authorization; immutable proposals, expirations and idempotence.
- Pydantic schemas forbid extra fields and reject invalid/nonfinite fee inputs.
- Opaque HttpOnly cookies, SameSite=Strict, same-origin checks, custom mutation header, CSP and escaped rendering.
- No secrets or private form data in structural logs. Provider response bodies are not surfaced on errors.
- Five failed verification attempts lock a session. Per-session request limits and bounded model steps/time/context.
- TLS verification remains enabled. Secrets live in ignored `.env` or injected process variables.

## Residual risks and governance

This is a local, single-worker demonstration, not deployment certification. A client can create new sessions to
evade session-level limits. Add account/IP rate limits, SSO, real verified identities, per-officer roles, TLS termination,
audit retention and operational monitoring for deployment. Do not expose the local demo to the public Internet.
Regex redaction is a precaution, not comprehensive PII detection. Do not type real identity data into chat.
Public conversation text can contain sensitive material despite minimization; synthetic input only.

Session expiry is enforced but old rows are not automatically purged. Define and implement retention and deletion
for all persisted records before real use. Officer tokens are entered transiently in the page, never localStorage.
Clearing a session cancels unconfirmed proposals; an already citizen-confirmed finance request remains in the officer
queue for auditability. No email reporting is sent automatically.

PDPL and SDAIA AI ethics considerations: data minimization, purpose limitation, visible simulation status,
human oversight, honest uncertainty, and reviewable evidence. This note is an engineering analysis, not legal advice.
