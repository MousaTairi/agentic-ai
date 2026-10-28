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
from .schemas import Fee, Permit, Reply, Search, Slots
from .storage import Store

READ_SCHEMAS = {"search_policies": Search, "compute_fee": Fee, "get_permit": Permit, "list_inspection_slots": Slots}
SCHEMAS = READ_SCHEMAS | WRITE_SCHEMAS
DESCRIPTIONS = {
    "search_policies": "Retrieve official bilingual policy evidence. Cite POL-xx IDs. Required for policy answers.",
    "compute_fee": "Calculate a fee from POL-02; required before quoting calculated fees.",
    "get_permit": "Get one application's status after identity verification through the UI. Never guess status.",
    "list_inspection_slots": "List available district inspection slots in a date range of at most 31 days.",
    "book_inspection": "PROPOSE a booking of a listed slot. Requires verified application; UI confirmation executes it.",
    "reschedule_inspection": "PROPOSE rescheduling a verified application's inspection. UI confirmation required.",
    "request_refund": "PROPOSE a refund request. UI confirmation required; >1000 SAR also needs finance approval.",
}
TOOLS = [{"type": "function", "function": {"name": name, "description": DESCRIPTIONS[name],
          "parameters": schema.model_json_schema()}} for name, schema in SCHEMAS.items()]


class Model(Protocol):
    async def complete(self, messages: list[dict], settings: Settings) -> dict: ...


class OpenRouter:
    async def complete(self, messages: list[dict], settings: Settings) -> dict:
        if not settings.api_key:
            raise RuntimeError("AI API key is not configured. Set OPENROUTER_API_KEY on the server.")
        async with httpx.AsyncClient(timeout=25) as client:
            for attempt in range(2):
                response = await client.post("https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.api_key}"},
                    json={"model": settings.model, "messages": messages, "tools": TOOLS,
                          "max_tokens": settings.max_tokens, "temperature": 0,
                          "provider": {"require_parameters": True}})
                if response.status_code in (429, 502, 503) and attempt == 0:
                    await asyncio.sleep(1)
                    continue
                if response.is_error:
                    # Do not log provider bodies; they can echo credentials or private input.
                    raise RuntimeError(f"AI provider returned HTTP {response.status_code}; retry later.")
                return response.json()
        raise RuntimeError("AI provider unavailable.")


@asynccontextmanager
async def bridge(settings: Settings) -> AsyncIterator[ClientSession]:
    env = dict(os.environ)
    env["RAFEEQ_RUNTIME"] = str(settings.runtime.resolve())
    # Read-only subprocess has no need for provider or officer credentials.
    env.pop("OPENROUTER_API_KEY", None)
    env.pop("RAFEEQ_OFFICER_TOKEN", None)
    env["RAFEEQ_NO_DOTENV"] = "1"
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
        if name in WRITE_SCHEMAS:
            return {"ok": True, "data": propose(store, sid, name, args)}
        if name == "get_permit":
            return {"ok": True, "data": permit_info(store, sid, args["permit_id"])}
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
    # Private application facts stay in the database and are re-read after authorization each turn.
    system = (PROJECT / "AGENTS.md").read_text()
    system += "\nActual date: " + datetime.now(ZoneInfo("Asia/Riyadh")).date().isoformat()
    system += ". Municipal calculations use the explicitly labelled simulation clock."
    messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": redact(message)}]
    used_in, used_out, reserved, steps = 0, 0, 0., 0
    called: list[str] = []
    final, stopped = "", "steps"
    started = time.monotonic()
    provider = model or OpenRouter()
    try:
        async with asyncio.timeout(settings.deadline_seconds), bridge(settings) as mcp:
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
                except (RuntimeError, httpx.HTTPError):
                    stopped = "provider_error"
                    break
                steps += 1
                usage = response.get("usage", {})
                used_in += usage.get("prompt_tokens", 0)
                used_out += usage.get("completion_tokens", 0)
                msg = response["choices"][0]["message"]
                calls = msg.get("tool_calls") or []
                messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
                if not calls:
                    final = redact(msg.get("content") or "")
                    stopped = "completed" if final else "empty_response"
                    break
                if len(calls) > 4:
                    stopped = "tool_budget"
                    break
                for call in calls:
                    name = call["function"]["name"]
                    result = await dispatch(name, call["function"]["arguments"], store, sid, mcp, settings.configuration)
                    called.append(name)
                    store.event(trace, "tool", name=name, ok=result.get("ok", False))
                    content = json.dumps(result, ensure_ascii=False)
                    if len(content) > 15000:
                        content = json.dumps({"ok": False, "error": "Result exceeds budget. Narrow your query."})
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})
    except TimeoutError:
        stopped = "deadline"
    except (RuntimeError, httpx.HTTPError):
        stopped = "provider_error"
    if not final:
        ar = bool(re.search(r"[\u0600-\u06ff]", message))
        final = ("تعذر إكمال الطلب. تحقق من إعداد مفتاح الخدمة أو حاول مجددًا. لم يتم تنفيذ أي إجراء دون تأكيد."
                 if ar else "I couldn't complete this turn. Check the server API key or retry. No action executes without confirmation.")
    with store.connect() as db:
        # Do not persist raw chat: it can contain identity digits or private record excerpts.
        # Store a bounded, non-sensitive task/language preference for conversational continuity.
        private = any(t in called for t in ("get_permit", *WRITE_SCHEMAS)) or bool(
            re.search(r"(?:BLD|REN|SGN|FTR|EVT)-\d{5}|\b(?:ID|mobile|identity)\b|هوية|جوال", message, re.I))
        safe_user = ("Citizen wrote in Arabic." if re.search(r"[\u0600-\u06ff]", message)
                     else "Citizen wrote in English.") if private else redact(message)
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
    usage_out = {"input_tokens": used_in, "output_tokens": used_out, "model_steps": steps,
                 "reserved_upper_usd": round(reserved, 6), "pricing_is_configured_estimate": True}
    store.event(trace, "turn", stopped=stopped, steps=steps, seconds=round(time.monotonic() - started, 3),
                session_hash=store.trace_session(sid), **{k: v for k, v in usage_out.items() if k != "model_steps"})
    return Reply(reply=final, tools=called, actions=actions, stopped=stopped, usage=usage_out, trace_id=trace)
