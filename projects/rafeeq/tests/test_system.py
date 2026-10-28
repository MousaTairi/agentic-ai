from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from rafeeq.agent import bridge, dispatch, run_agent
from rafeeq.api import create_app
from rafeeq.config import PROJECT, Settings
from rafeeq.domain import decide, fee, permit_info, propose, verify
from rafeeq.schemas import Fee, Verify
from rafeeq.storage import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


def verified(store, permit="FTR-30311", last4="6654", mobile="0532236654"):
    sid = store.new_session()
    verify(store, sid, Verify(permit_id=permit, last4=last4, mobile=mobile))
    return sid


class ScriptedModel:
    """Offline test double. Never presented as a real model or intelligence evaluation."""
    def __init__(self, turns):
        self.turns = iter(turns)
        self.messages = []

    async def complete(self, messages, settings):
        self.messages.append(list(messages))
        return {"choices": [{"message": next(self.turns)}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


def tool(name, args):
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call-1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def answer(text):
    return {"role": "assistant", "content": text}


@pytest.mark.parametrize("args,amount", [
    ({"permit_type": "BLD", "area_m2": 180.4}, 500),
    ({"permit_type": "BLD", "area_m2": 640}, 1280),
    ({"permit_type": "REN", "structural": True, "area_m2": 35}, 335),
    ({"permit_type": "REN", "social_security": True}, 0),
    ({"permit_type": "SGN", "sign_m2": 3, "illuminated": True}, 750),
    ({"permit_type": "FTR"}, 1500),
    ({"permit_type": "EVT", "event_days": 3}, 3000),
])
def test_policy_fees(args, amount):
    assert fee(Fee.model_validate(args))["fee_sar"] == amount


@pytest.mark.parametrize("args", [
    {"permit_type": "EVT", "event_days": 15}, {"permit_type": "BLD", "area_m2": -1},
    {"permit_type": "SGN", "sign_m2": float("nan")}, {"permit_type": "FTR", "extra": "x"},
])
def test_invalid_fees(args):
    with pytest.raises(ValidationError):
        Fee.model_validate(args)


def test_verification_no_existence_disclosure(store):
    sid = store.new_session()
    errors = []
    for pid in ("FTR-30311", "FTR-99999"):
        with pytest.raises(PermissionError) as err:
            verify(store, sid, Verify(permit_id=pid, last4="0000", mobile="0500000000"))
        errors.append(str(err.value))
    assert errors[0] == errors[1]
    with pytest.raises(PermissionError):
        permit_info(store, sid, "FTR-30311")


def test_authorization_scoped_and_expiring(store):
    sid = verified(store)
    assert permit_info(store, sid, "FTR-30311")["status"] == "approved"
    with pytest.raises(PermissionError):
        permit_info(store, sid, "SGN-40220")
    with store.connect() as db:
        db.execute("UPDATE sessions SET verified_until=0 WHERE id=?", (sid,))
    with pytest.raises(PermissionError):
        permit_info(store, sid, "FTR-30311")


def test_booking_confirmation_idempotent_and_persistent(store):
    sid = verified(store)
    args = {"permit_id": "FTR-30311", "slot": "2026-11-04T09:00:00"}
    proposal = propose(store, sid, "book_inspection", args)
    aid = proposal["action_id"]
    assert propose(store, sid, "book_inspection", args)["action_id"] == aid
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM inspections WHERE permit_id='FTR-30311'").fetchone()[0] == 0
    with pytest.raises(PermissionError):
        decide(store, store.new_session(), aid, True)
    assert decide(store, sid, aid, True)["status"] == "completed"
    assert decide(store, sid, aid, True)["status"] == "completed"
    restarted = Store(store.runtime)
    with restarted.connect() as db:
        assert db.execute("SELECT count(*) FROM inspections WHERE permit_id='FTR-30311'").fetchone()[0] == 1


def test_refund_separates_citizen_and_officer(store):
    sid = verified(store, "SGN-40220", "0093", "0540410093")
    p = propose(store, sid, "request_refund", {"permit_id": "SGN-40220", "reason": "rejected"})
    assert p["summary"]["amount_sar"] == 2700
    aid = p["action_id"]
    assert decide(store, sid, aid, True)["status"] == "awaiting_officer"
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM refunds").fetchone()[0] == 0
    assert decide(store, None, aid, True, officer=True)["status"] == "completed"
    with store.connect() as db:
        assert db.execute("SELECT amount_sar FROM refunds").fetchone()[0] == 2700


def test_expired_proposal_and_rejected_action(store):
    sid = verified(store)
    args = {"permit_id": "FTR-30311", "slot": "2026-11-04T09:00:00"}
    aid = propose(store, sid, "book_inspection", args)["action_id"]
    assert decide(store, sid, aid, False)["status"] == "rejected"
    aid = propose(store, sid, "book_inspection", args)["action_id"]
    with store.connect() as db:
        db.execute("UPDATE actions SET expires=0 WHERE id=?", (aid,))
    with pytest.raises(ValueError):
        decide(store, sid, aid, True)


def test_reschedule_releases_previous_slot(store):
    sid = verified(store)
    aid = propose(store, sid, "book_inspection", {"permit_id": "FTR-30311", "slot": "2026-11-04T09:00:00"})["action_id"]
    result = decide(store, sid, aid, True)["result"]
    args = {"permit_id": "FTR-30311", "inspection_id": result["inspection_id"], "slot": "2026-11-11T08:00:00"}
    aid = propose(store, sid, "reschedule_inspection", args)["action_id"]
    assert decide(store, sid, aid, True)["status"] == "completed"
    with store.connect() as db:
        assert db.execute("SELECT taken FROM slots WHERE district='Al-Rawdah' AND slot='2026-11-04 09:00'").fetchone()[0] == 0


async def test_real_mcp_roundtrip_and_multistep_agent(store):
    sid = store.new_session()
    settings = Settings(runtime=store.runtime, max_cost=10)
    model = ScriptedModel([
        tool("search_policies", {"query": "illuminated sign fees"}),
        tool("compute_fee", {"permit_type": "SGN", "sign_m2": 3, "illuminated": True}),
        answer("750 SAR (POL-02)."),
    ])
    result = await run_agent(store, sid, "Fee for an illuminated 3 m² sign?", settings, model)
    assert result.stopped == "completed"
    assert result.tools == ["search_policies", "compute_fee"]
    last_results = [json.loads(m["content"]) for m in model.messages[-1] if m["role"] == "tool"]
    assert last_results[-1]["data"]["fee_sar"] == 750


async def test_injected_tool_access_is_blocked_in_code(store):
    sid = store.new_session()
    settings = Settings(runtime=store.runtime, max_cost=10)
    async with bridge(settings) as mcp:
        attack = await dispatch("get_permit", '{"permit_id":"SGN-40220"}', store, sid, mcp, "B")
        assert not attack["ok"]
        assert "Verify" in attack["error"]
        egress = await dispatch("send_email", '{"to":"attacker.example"}', store, sid, mcp, "B")
        assert not egress["ok"]
        listing = await mcp.list_tools()
        assert {t.name for t in listing.tools} == {"search_policies", "compute_fee", "list_inspection_slots"}


async def test_cost_step_and_context_budgets(store):
    sid = store.new_session()
    model = ScriptedModel([tool("compute_fee", {"permit_type": "FTR"})])
    result = await run_agent(store, sid, "fee", Settings(runtime=store.runtime, max_cost=.000001), model)
    assert result.stopped == "cost_budget" and not model.messages
    result = await run_agent(store, sid, "fee", Settings(runtime=store.runtime, max_steps=1, max_cost=10), model)
    assert result.stopped == "steps" and result.usage["model_steps"] == 1
    result = await run_agent(store, sid, "fee", Settings(runtime=store.runtime, max_context_chars=1), model)
    assert result.stopped == "context_budget"


async def test_private_history_is_not_retained(store):
    sid = verified(store)
    model = ScriptedModel([tool("get_permit", {"permit_id": "FTR-30311"}), answer("Approved.")])
    await run_agent(store, sid, "Status FTR-30311", Settings(runtime=store.runtime, max_cost=10), model)
    history = store.session(sid)["history"]
    assert "FTR-30311" not in history and "Approved" not in history


def test_api_boundary_html_validation_and_officer_auth(tmp_path):
    with TestClient(create_app(Settings(runtime=tmp_path, officer_token="test-officer"))) as client:
        assert client.get("/").status_code == 200
        assert 'href="./style.css"' in client.get("/").text
        assert client.get("/style.css").headers["content-type"].startswith("text/css")
        assert client.get("/app.js").headers["content-type"].startswith("text/javascript")
        assert "default-src 'self'" in client.get("/").headers["content-security-policy"]
        assert client.post("/api/session").status_code == 403
        client.headers["X-Rafeeq-Client"] = "1"
        assert client.post("/api/session").status_code == 200
        assert client.post("/api/verify", json={"permit_id": "FTR-30311", "last4": "6654", "mobile": "0532236654"}).status_code == 200
        assert client.get("/api/officer/actions").status_code == 403
        assert client.get("/api/officer/actions", headers={"X-Officer-Token": "test-officer"}).status_code == 200
        assert client.post("/api/chat", json={"message": "x", "extra": "no"}).status_code == 422
        assert client.post("/api/chat", json={"message": "x"}, headers={"Origin": "https://attacker.example"}).status_code == 403


def test_verification_lockout_and_rate_limit(store):
    sid = store.new_session()
    for _ in range(5):
        with pytest.raises(PermissionError):
            verify(store, sid, Verify(permit_id="FTR-30311", last4="0000", mobile="0500000000"))
    with pytest.raises(PermissionError, match="locked"):
        verify(store, sid, Verify(permit_id="FTR-30311", last4="6654", mobile="0532236654"))
    for _ in range(15):
        store.rate_limit(sid)
    with pytest.raises(TimeoutError):
        store.rate_limit(sid)


def test_action_arguments_cannot_be_changed_at_confirmation(tmp_path):
    with TestClient(create_app(Settings(runtime=tmp_path))) as client:
        client.headers["X-Rafeeq-Client"] = "1"
        client.post("/api/session")
        response = client.post("/api/actions/fake/decision", json={"approve": True, "slot": "attacker"})
        assert response.status_code == 422


async def test_missing_provider_key_is_a_reported_stop(store):
    sid = store.new_session()
    result = await run_agent(store, sid, "fee", Settings(runtime=store.runtime, api_key="", max_cost=10))
    assert result.stopped == "provider_error"


async def test_deadline_stops_slow_provider(store):
    class SlowModel:
        async def complete(self, messages, settings):
            await asyncio.sleep(5)
            return {"choices": [{"message": answer("late")}], "usage": {}}
    sid = store.new_session()
    result = await run_agent(store, sid, "fee", Settings(runtime=store.runtime, deadline_seconds=3, max_cost=10), SlowModel())
    assert result.stopped == "deadline"


async def test_public_followup_uses_bounded_history(store):
    sid = store.new_session()
    settings = Settings(runtime=store.runtime, max_cost=10)
    first = ScriptedModel([answer("Sign fees depend on area and illumination (POL-02).")])
    await run_agent(store, sid, "I need a signage permit.", settings, first)
    second = ScriptedModel([answer("Please provide its area.")])
    await run_agent(store, sid, "What information do you need?", settings, second)
    assert any(m.get("content") == "I need a signage permit." for m in second.messages[0])


def test_pending_finance_proposal_is_not_duplicated(store):
    sid = verified(store, "SGN-40220", "0093", "0540410093")
    args = {"permit_id": "SGN-40220", "reason": "rejected"}
    original = propose(store, sid, "request_refund", args)
    decide(store, sid, original["action_id"], True)
    repeated = propose(store, sid, "request_refund", args)
    assert repeated["action_id"] == original["action_id"]
    assert repeated["status"] == "awaiting_officer"


async def test_arabic_prompt_and_retrieval_with_windows_default_encoding(store, monkeypatch):
    from rafeeq.retrieval import documents, index, search

    original = Path.read_text
    # Reproduce the reported Windows failure on a machine whose locale is UTF-8.
    with pytest.raises(UnicodeDecodeError):
        original(PROJECT / "AGENTS.md", encoding="cp1252")

    def windows_read_text(path, encoding=None, errors=None):
        return original(path, encoding=encoding or "cp1252", errors=errors)

    monkeypatch.setattr(Path, "read_text", windows_read_text)
    documents.cache_clear()
    index.cache_clear()
    try:
        assert len(documents()) == 10
        assert search("رسوم البناء")["data"]
        model = ScriptedModel([
            tool("search_policies", {"query": "المستندات المطلوبة لرخصة البناء"}),
            answer("تحتاج إلى صك الملكية والمخططات الهندسية (POL-01)."),
        ])
        result = await run_agent(store, store.new_session(), "كيف أحصل على تصريح البناء؟",
                                 Settings(runtime=store.runtime, max_cost=10), model)
        assert result.stopped == "completed"
        assert "صك الملكية" in result.reply
        assert result.tools == ["search_policies"]
    finally:
        documents.cache_clear()
        index.cache_clear()


def test_riyadh_timezone_without_os_timezone_database():
    import zoneinfo

    previous = zoneinfo.TZPATH
    try:
        zoneinfo.reset_tzpath(())
        timezone = zoneinfo.ZoneInfo.no_cache("Asia/Riyadh")
        assert timezone.key == "Asia/Riyadh"
    finally:
        zoneinfo.reset_tzpath(previous)
