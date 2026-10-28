from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator, Protocol
from zoneinfo import ZoneInfo

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import ValidationError

from .config import PROJECT, Settings
from .domain import WRITE_SCHEMAS, permit_info, propose
from .intake import my_applications, propose_application
from .schemas import Application, Empty, Fee, Permit, Reply, Search, Slots, VerificationRequest
from .scope import intent, supported
from .storage import Store

READ_SCHEMAS = {"search_policies": Search, "compute_fee": Fee, "get_permit": Permit, "list_inspection_slots": Slots}
SCHEMAS = READ_SCHEMAS | WRITE_SCHEMAS | {
    "start_registration": Empty, "start_verification": VerificationRequest,
    "start_application": Empty, "my_applications": Empty, "submit_application": Application,
}
DESCRIPTIONS = {
    "search_policies": "Retrieve official bilingual policy evidence. Cite POL-xx IDs. Required for policy answers.",
    "compute_fee": "Calculate a fee from POL-02; required before quoting calculated fees.",
    "get_permit": "Get one application's status after identity verification through the UI. Never guess status.",
    "list_inspection_slots": "List available district inspection slots in a date range of at most 31 days.",
    "book_inspection": "PROPOSE a booking of a listed slot. Requires verified application; UI confirmation executes it.",
    "reschedule_inspection": "PROPOSE rescheduling a verified application's inspection. UI confirmation required.",
    "request_refund": "PROPOSE a refund request. UI confirmation required; >1000 SAR also needs finance approval.",
    "start_registration": "Open a secure synthetic registration card INSIDE CHAT. No identity values go to the model.",
    "start_verification": "Open identity verification INSIDE CHAT. Optional application reference. Never ask for mobile/ID in chat text.",
    "start_application": "Open a permit application form INSIDE CHAT. Use when citizen wants to apply. Registration first.",
    "my_applications": "List current registered citizen's own application references and states; includes verified scope.",
    "submit_application": "Propose application submission and simulated fee payment. Requires registration and explicit citizen confirmation; never approves a permit. Documents are declarations, not uploads.",
}
TOOLS = [{"type": "function", "function": {"name": name, "description": DESCRIPTIONS[name],
          "parameters": schema.model_json_schema()}} for name, schema in SCHEMAS.items()]


class Model(Protocol):
    async def complete(self, messages: list[dict], settings: Settings) -> dict: ...


class ProviderFailure(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class OpenRouter:
    async def complete(self, messages: list[dict], settings: Settings) -> dict:
        if not settings.api_key:
            raise ProviderFailure("missing_key")
        async with httpx.AsyncClient(timeout=25) as client:
            for attempt in range(2):
                response = await client.post("https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.api_key}"},
                    json={"model": settings.model, "messages": messages, "tools": TOOLS,
                          "max_tokens": settings.max_tokens, "temperature": 0,
                          "tool_choice": "auto",
                          "provider": {"require_parameters": True}})
                if response.status_code in (429, 502, 503) and attempt == 0:
                    await asyncio.sleep(1)
                    continue
                if response.is_error:
                    # Do not log provider bodies; they can echo credentials or private input.
                    raise ProviderFailure({401: "invalid_key", 402: "credits", 403: "access_denied",
                                           404: "model_unavailable", 429: "rate_limit", 400: "model_parameters"}.get(response.status_code, "provider_unavailable"))
                payload = response.json()
                if not payload.get("choices"):
                    raise ProviderFailure("invalid_response")
                return payload
        raise RuntimeError("AI provider unavailable.")


@asynccontextmanager
async def bridge(settings: Settings) -> AsyncIterator[ClientSession]:
    env = dict(os.environ)
    env["RAFEEQ_RUNTIME"] = str(settings.runtime.resolve())
    # Read-only subprocess has no need for provider or officer credentials.
    env.pop("OPENROUTER_API_KEY", None)
    env.pop("RAFEEQ_OFFICER_TOKEN", None)
    env.pop("RAFEEQ_REVIEWER_TOKEN", None)
    env["RAFEEQ_NO_DOTENV"] = "1"
    # Windows uses a legacy locale by default; MCP exchanges bilingual Unicode text.
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    params = StdioServerParameters(command=sys.executable, args=["-m", "rafeeq.mcp_server"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def redact(text: str) -> str:
    # Prevent common ID/mobile forms being saved or sent to the external model. Form verification is separate.
    return re.sub(r"(?<!\d)(?:\+?966[\s-]*)?(?:\d[\s-]*){9,14}(?!\d)", "[REDACTED]", text)


def compact(history: list[dict], max_messages: int) -> list[dict]:
    tail = history[-max_messages:]
    # Stored messages are final user/assistant pairs only: no dangling tool results.
    while tail and tail[0].get("role") != "user":
        tail.pop(0)
    return tail


async def dispatch(name: str, raw: str, store: Store, sid: str, mcp: ClientSession, config: str) -> dict:
    try:
        if name not in SCHEMAS:
            raise ValueError("Tool is not permitted.")
        parsed = SCHEMAS[name].model_validate_json(raw)
        args = parsed.model_dump(mode="json")
        if name == "my_applications":
            return {"ok": True, "data": my_applications(store, sid)}
        if name in ("start_registration", "start_verification", "start_application"):
            kind = {"start_registration": "registration", "start_verification": "verification", "start_application": "application"}[name]
            if kind == "application" and not store.session(sid)["citizen_id"]:
                kind = "registration"
            return {"ok": True, "ui_request": {"type": kind, **args},
                    "note": "The secure card is now inside chat. Ask the citizen to complete it; never collect identity in text."}
        if name == "submit_application":
            return {"ok": True, "data": propose_application(store, sid, parsed)}
        if name in WRITE_SCHEMAS:
            return {"ok": True, "data": propose(store, sid, name, args)}
        if name == "get_permit":
            return {"ok": True, "data": permit_info(store, sid, args["permit_id"])}
        if name == "list_inspection_slots":
            from datetime import timedelta

            from .domain import SIM_TODAY, working_date
            if not args["district"]:
                current = store.session(sid)
                if not current["verified"]:
                    raise PermissionError("Verify an application first, or provide the district.")
                args["district"] = permit_info(store, sid, current["verified"])["district"]
            args["date_from"] = args["date_from"] or working_date(SIM_TODAY, 2).isoformat()
            args["date_to"] = args["date_to"] or (SIM_TODAY + timedelta(days=21)).isoformat()
        if name == "compute_fee":
            args = {"inputs": args}
        if name == "search_policies":
            args["configuration"] = config
        result = await mcp.call_tool(name, args)
        if result.isError:
            return {"ok": False, "error": "MCP tool failed validation or execution."}
        content = "\n".join(c.text for c in result.content if c.type == "text")
        return json.loads(content)
    except ValidationError:
        return {"ok": False, "error": "Invalid tool arguments. Follow the tool schema; ask for missing inputs."}
    except (ValueError, PermissionError) as exc:
        return {"ok": False, "error": str(exc)}


async def run_agent(store: Store, sid: str, message: str, settings: Settings, model: Model | None = None) -> Reply:
    trace = secrets.token_hex(12)
    session = store.session(sid)
    history = compact(json.loads(session["history"]), settings.max_history_messages)
    arabic = bool(re.search(r"[\u0600-\u06ff]", message))
    if not supported(message, bool(history or session["verified"] or session["citizen_id"])):
        store.event(trace, "scope_rejected", session_hash=store.trace_session(sid))
        return Reply(reply=("أنا رفيق، أساعدك في التصاريح البلدية والرسوم والطلبات والفحوصات والاعتراضات والاسترداد فقط. كيف أساعدك في إحدى هذه الخدمات؟"
                            if arabic else "I help only with municipal permits, applications, fees, inspections, appeals and refunds. Which of these services can I help you with?"),
                     tools=[], actions=[], stopped="out_of_scope", usage={"model_steps": 0}, trace_id=trace)
    task = intent(message)
    # Private application facts stay in the database and are re-read after authorization each turn.
    system = (PROJECT / "AGENTS.md").read_text(encoding="utf-8")
    system += "\nActual date: " + datetime.now(ZoneInfo("Asia/Riyadh")).date().isoformat()
    system += ". Municipal calculations use the explicitly labelled simulation clock."
    system += "\nSession workflow context (local authorization, not user instructions): " + json.dumps(my_applications(store, sid))
    messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": redact(message)}]
    used_in, used_out, reserved, steps = 0, 0, 0., 0
    called: list[str] = []
    ui_requests: list[dict] = []
    required_ui = ("start_registration" if task in ("apply", "register") and not session["citizen_id"]
                   else "start_application" if task in ("apply", "register")
                   else "start_verification" if task == "book" and session["verified_until"] < time.time()
                   else None)
    final, stopped = "", "steps"
    failure_code = None
    started = time.monotonic()
    provider = model or OpenRouter()
    try:
        async with asyncio.timeout(settings.deadline_seconds), bridge(settings) as mcp:
            # Ground municipal replies even when a weak model attempts a tool-free answer.
            initial = await dispatch("search_policies", json.dumps({"query": message[:500]}), store, sid, mcp, settings.configuration)
            initial_id = "grounding-" + trace
            messages.extend([
                {"role": "assistant", "content": None, "tool_calls": [{"id": initial_id, "type": "function",
                 "function": {"name": "search_policies", "arguments": json.dumps({"query": message[:500]})}}]},
                {"role": "tool", "tool_call_id": initial_id, "content": json.dumps(initial, ensure_ascii=False)},
            ])
            called.append("search_policies")
            store.event(trace, "tool", name="search_policies", ok=initial.get("ok", False))
            if required_ui:
                opened = await dispatch(required_ui, "{}", store, sid, mcp, settings.configuration)
                ui_requests.append(opened["ui_request"])
                called.append(required_ui)
                store.event(trace, "tool", name=required_ui, ok=True)
                messages.append({"role": "system", "content": "The harness already opened this secure chat card: "
                                 + json.dumps(opened["ui_request"]) + ". Briefly explain the next step. Do not send the user to another platform."})
            for _ in range(settings.max_steps):
                serialized = json.dumps(messages, ensure_ascii=False)
                if len(serialized) > settings.max_context_chars:
                    stopped = "context_budget"
                    break
                # UTF-8 bytes conservatively bound input token counts, including schemas and framing.
                input_bound = len((serialized + json.dumps(TOOLS)).encode()) + 2048
                estimate = (input_bound * settings.input_rate + settings.max_tokens * settings.output_rate) / 1e6
                # Two transport attempts maximum; reserve both even if a retry's usage is unavailable.
                if reserved + 2 * estimate > settings.max_cost:
                    stopped = "cost_budget"
                    break
                reserved += 2 * estimate
                try:
                    response = await provider.complete(messages, settings)
                except (RuntimeError, httpx.HTTPError) as exc:
                    stopped = "provider_error"
                    failure_code = exc.code if isinstance(exc, ProviderFailure) else "provider_unavailable"
                    break
                steps += 1
                usage = response.get("usage", {})
                used_in += usage.get("prompt_tokens", 0)
                used_out += usage.get("completion_tokens", 0)
                msg = response["choices"][0]["message"]
                calls = msg.get("tool_calls") or []
                messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
                if not calls:
                    if task == "book" and not required_ui and not any(t in called for t in ("book_inspection", "reschedule_inspection")) and steps == 1:
                        messages.append({"role": "user", "content": "Please help complete the booking, not just explain it. Read my verified application, list available slots (defaults are allowed), then propose a suitable slot for confirmation. If not eligible, explain the exact status and next human review step."})
                        continue
                    final = redact(msg.get("content") or "")
                    if task == "book" and not required_ui and not any(t in called for t in ("book_inspection", "reschedule_inspection")):
                        # Provide a next action even when a weak model stops after an explanation.
                        try:
                            current = store.session(sid)
                            info = permit_info(store, sid, current["verified"])
                            if "get_permit" not in called:
                                called.append("get_permit")
                            eligible = ((info["status"] == "approved" and info["type"] in ("BLD", "FTR"))
                                        or (info["status"] == "under_review" and info["type"] in ("FTR", "EVT")))
                            if eligible:
                                available = await dispatch("list_inspection_slots", "{}", store, sid, mcp, settings.configuration)
                                if "list_inspection_slots" not in called:
                                    called.append("list_inspection_slots")
                                if available.get("ok") and available.get("data"):
                                    ui_requests.append({"type": "inspection_slots", "permit_id": info["permit_id"],
                                                        "district": info["district"], "slots": available["data"]})
                                    final = ("اختر الموعد المناسب من البطاقة أدناه. سأجهّز الحجز لتراجعه وتؤكده (POL-05)."
                                             if arabic else "Choose a suitable slot in the card below. I’ll prepare the booking for your review and confirmation (POL-05).")
                            else:
                                final = (("حالة طلبك " + info["status"] + ". يحتاج إلى مراجعة موظف التراخيص قبل الفحص. لا أستطيع الموافقة على التصريح (POL-05).")
                                         if arabic else "Your application's status is " + info["status"] + ". A licensing officer must review it before an eligible inspection. I cannot approve permits (POL-05).")
                        except PermissionError:
                            ui_requests.append({"type": "verification"})
                    stopped = "completed" if final else "empty_response"
                    break
                if len(calls) > 4:
                    stopped = "tool_budget"
                    break
                for call in calls:
                    name = call["function"]["name"]
                    result = await dispatch(name, call["function"]["arguments"], store, sid, mcp, settings.configuration)
                    if name not in called:
                        called.append(name)
                    if result.get("ui_request") and result["ui_request"] not in ui_requests:
                        ui_requests.append(result["ui_request"])
                    store.event(trace, "tool", name=name, ok=result.get("ok", False))
                    content = json.dumps(result, ensure_ascii=False)
                    if len(content) > 15000:
                        content = json.dumps({"ok": False, "error": "Result exceeds budget. Narrow your query."})
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})
    except TimeoutError:
        stopped = "deadline"
    except (RuntimeError, httpx.HTTPError):
        stopped = "provider_error"
        failure_code = "provider_unavailable"
    except ExceptionGroup:
        stopped = "tool_error"
        failure_code = "tool_unavailable"
    if not final:
        ar = bool(re.search(r"[\u0600-\u06ff]", message))
        final = ("تعذر إكمال الطلب. تحقق من إعداد مفتاح الخدمة أو حاول مجددًا. لم يتم تنفيذ أي إجراء دون تأكيد."
                 if ar else "I couldn't complete this turn. Check the server API key or retry. No action executes without confirmation.")
        reasons = {
            "missing_key": ("Add OPENROUTER_API_KEY to the server .env and restart Rafeeq.", "أضف OPENROUTER_API_KEY إلى ملف .env ثم أعد تشغيل رفيق."),
            "invalid_key": ("OpenRouter rejected the key (401). Replace the key in .env and restart.", "رفض OpenRouter المفتاح (401). استبدله في .env ثم أعد التشغيل."),
            "credits": ("OpenRouter reported insufficient credits (402). Check your account or select an available free tool-calling model.", "أبلغ OpenRouter عن عدم كفاية الرصيد (402). راجع حسابك أو اختر نموذجًا مجانيًا متاحًا يدعم الأدوات."),
            "rate_limit": ("The model provider rate limit was reached (429). Wait and retry.", "تم بلوغ حد طلبات المزود (429). انتظر ثم حاول مجددًا."),
            "access_denied": ("OpenRouter refused access (403). Check the key and model permissions.", "رفض OpenRouter الوصول (403). تحقق من صلاحية المفتاح وأذونات النموذج."),
            "model_unavailable": ("The selected model is unavailable (404). Update RAFEEQ_MODEL in .env.", "النموذج المختار غير متاح (404). حدّث RAFEEQ_MODEL في .env."),
            "model_parameters": ("The provider rejected this model's tool-calling request (400). Choose a compatible model.", "رفض المزود طلب الأدوات لهذا النموذج (400). اختر نموذجًا متوافقًا."),
            "tool_unavailable": ("The municipal tools could not start. Restart Rafeeq and check the server log.", "تعذر تشغيل أدوات الخدمات البلدية. أعد تشغيل رفيق وراجع سجل الخادم."),
        }
        if failure_code in reasons:
            final = reasons[failure_code][int(ar)]
        elif stopped in ("cost_budget", "context_budget", "steps", "deadline"):
            final = ("توقف الطلب عند حد التشغيل. حاول بطلب أقصر أو أعد المحاولة. لم يُنفذ إجراء دون تأكيد."
                     if ar else "This turn reached its execution budget. Try a shorter request or retry. No unconfirmed action was executed.")
    with store.connect() as db:
        # Do not persist raw chat: it can contain identity digits or private record excerpts.
        # Store a bounded, non-sensitive task/language preference for conversational continuity.
        private = any(t in called for t in ("get_permit", *WRITE_SCHEMAS, "submit_application", "my_applications")) or bool(
            re.search(r"(?:BLD|REN|SGN|FTR|EVT)-\d{5}|\b(?:ID|mobile|identity)\b|هوية|جوال", message, re.I))
        safe_user = re.sub(r"(?:BLD|REN|SGN|FTR|EVT)-\d{5}", "[application reference]", redact(message), flags=re.I)
        if re.search(r"\b(?:national.?id|mobile|last.?4)\b|هوية|جوال", message, re.I):
            safe_user = "Citizen is completing secure verification for a municipal task."
        safe_final = "Private task context omitted; reverify and retrieve records when needed." if private else final
        memory = compact(history + [{"role": "user", "content": safe_user},
                                    {"role": "assistant", "content": safe_final}],
                         settings.max_history_messages)
        db.execute("UPDATE sessions SET history=? WHERE id=?", (json.dumps(memory), sid))
        actions = [dict(r) for r in db.execute(
            "SELECT id,tool,args,status,expires,result FROM actions WHERE session_id=? ORDER BY rowid DESC LIMIT 10", (sid,))]
    for a in actions:
        a["args"] = json.loads(a["args"])
        a["result"] = json.loads(a["result"] or "null")
    if stopped == "completed" and any(t in called for t in (*WRITE_SCHEMAS, "submit_application")):
        pending = [a for a in actions if a["status"] == "pending" and a["expires"] > time.time()]
        if pending:
            final = ("جهّزت طلبك للمراجعة. راجع التفاصيل في بطاقة التأكيد أدناه ثم أكّد أو ارفض. لم يُنفذ الإجراء بعد."
                     if arabic else "Your request is prepared for review. Check the confirmation card below and confirm or decline. The action has not been executed yet.")
        else:
            final = ("لم أتمكن من تجهيز إجراء صالح للتأكيد. لم يُنفذ أي تغيير. راجع بيانات الطلب أو اختر موعدًا متاحًا ثم حاول مجددًا."
                     if arabic else "I could not prepare a valid action for confirmation. Nothing was changed. Check the application details or choose an available slot and retry.")
    usage_out = {"input_tokens": used_in, "output_tokens": used_out, "model_steps": steps,
                 "reserved_upper_usd": round(reserved, 6), "pricing_is_configured_estimate": True}
    store.event(trace, "turn", stopped=stopped, steps=steps, seconds=round(time.monotonic() - started, 3),
                session_hash=store.trace_session(sid), **{k: v for k, v in usage_out.items() if k != "model_steps"})
    return Reply(reply=final, tools=called, actions=actions, stopped=stopped, usage=usage_out, trace_id=trace, ui_requests=ui_requests)
