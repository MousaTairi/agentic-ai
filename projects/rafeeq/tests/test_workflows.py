from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from test_system import ScriptedModel, answer, tool

from rafeeq.agent import run_agent
from rafeeq.api import create_app
from rafeeq.config import Settings
from rafeeq.domain import decide, permit_info, verify
from rafeeq.intake import DOCUMENTS, begin_review, my_applications, propose_application, quote, register
from rafeeq.schemas import Application, Permit, Register, Verify
from rafeeq.storage import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)


@pytest.mark.parametrize("message", [
    "write code for sorting list desc", "Write Python code for me", "What is the weather?",
    "اكتب كود لترتيب قائمة", "اكتب قصيدة", "Give me a recipe", "Who is the president?",
])
async def test_scope_rejection_never_calls_model_even_after_municipal_turn(store, message):
    sid = store.new_session()
    with store.connect() as db:
        db.execute("UPDATE sessions SET history=? WHERE id=?",
                   (json.dumps([{"role": "user", "content": "permit fees"}, {"role": "assistant", "content": "POL-02"}]), sid))
    model = ScriptedModel([])
    reply = await run_agent(store, sid, message, Settings(runtime=store.runtime), model)
    assert reply.stopped == "out_of_scope"
    assert not reply.tools and not model.messages
    assert reply.usage["model_steps"] == 0


@pytest.mark.parametrize("configuration", ["A", "B"])
async def test_registration_then_application_submission_and_booking_workflow(store, configuration):
    settings = Settings(runtime=store.runtime, max_cost=10, configuration=configuration)
    sid = store.new_session()
    start = await run_agent(store, sid, "I want to apply for a food truck permit and book an inspection", settings,
                            ScriptedModel([answer("Complete the secure profile card below.")]))
    assert start.ui_requests == [{"type": "registration"}]
    assert "search_policies" in start.tools
    registration = Register(display_name="Synthetic citizen", last4="1234", mobile="0501231234", consent=True)
    register(store, sid, registration)
    next_turn = await run_agent(store, sid, "Continue my application for a food truck permit", settings,
                               ScriptedModel([answer("Complete the application card.")]))
    assert next_turn.ui_requests == [{"type": "application"}]
    application = Application(permit_type="FTR", district="Al-Rawdah", documents=DOCUMENTS["FTR"])
    draft = propose_application(store, sid, application)
    assert draft["summary"]["fee_sar"] == 1500
    assert not my_applications(store, sid)["applications"]
    result = decide(store, sid, draft["action_id"], True)
    pid = result["result"]["permit_id"]
    assert result["result"]["status"] == "submitted"
    assert decide(store, sid, draft["action_id"], True) == result
    assert len(my_applications(store, sid)["applications"]) == 1
    # A real human reviewer starts review; the assistant never approves a permit.
    assert begin_review(store, pid)["status"] == "under_review"
    model = ScriptedModel([
        tool("get_permit", {"permit_id": pid}),
        tool("list_inspection_slots", {}),
        tool("book_inspection", {"permit_id": pid, "slot": "2026-11-04T09:00:00"}),
        answer("Please confirm the proposed appointment."),
    ])
    booked = await run_agent(store, sid, "Book an inspection on 4 November at 09:00", settings, model)
    for name in ("search_policies", "get_permit", "list_inspection_slots", "book_inspection"):
        assert name in booked.tools
    pending = next(a for a in booked.actions if a["tool"] == "book_inspection")
    assert not permit_info(store, sid, pid)["inspections"]
    assert decide(store, sid, pending["id"], True)["status"] == "completed"
    assert len(permit_info(store, sid, pid)["inspections"]) == 1
    # The provider never sees registration fields or citizen display name.
    sent = json.dumps(model.messages)
    assert "0501231234" not in sent and "Synthetic citizen" not in sent and '"1234"' not in sent


async def test_weak_model_booking_still_offers_real_available_slots(store):
    sid = store.new_session()
    verify(store, sid, Verify(permit_id="ftr-30311", last4="٦٦٥٤", mobile="٠٥٣٢٢٣٦٦٥٤"))
    model = ScriptedModel([answer("Please choose a district."), answer("You should book online.")])
    result = await run_agent(store, sid, "احجز لي موعد فحص", Settings(runtime=store.runtime, max_cost=10), model)
    assert result.stopped == "completed"
    assert result.ui_requests[0]["type"] == "inspection_slots"
    assert result.ui_requests[0]["district"] == "Al-Rawdah"
    assert "2026-11-04 09:00" in result.ui_requests[0]["slots"]
    assert "list_inspection_slots" in result.tools


def test_intake_api_and_separate_reviewer_role(tmp_path):
    with TestClient(create_app(Settings(runtime=tmp_path, reviewer_token="test-reviewer", officer_token="test-finance"))) as client:
        client.headers["X-Rafeeq-Client"] = "1"
        client.post("/api/session")
        assert client.post("/api/register", json={"display_name": "Demo", "last4": "١٢٣٤", "mobile": "٠٥٠١٢٣١٢٣٤", "consent": True}).status_code == 200
        draft = client.post("/api/application-draft", json={"permit_type": "FTR", "district": "Al-Rawdah", "documents": []})
        assert draft.status_code == 200
        assert client.get("/api/me").json()["applications"] == []
        assert draft.json()["summary"]["missing_documents"]
        result = client.post('/api/actions/' + draft.json()["action_id"] + '/decision', json={"approve": True}).json()
        pid = result["result"]["permit_id"]
        assert result["result"]["status"] == "needs_info"
        assert client.post("/api/reviewer/begin-review", json={"permit_id": pid}).status_code == 403
        assert client.post("/api/reviewer/begin-review", json={"permit_id": pid}, headers={"X-Officer-Token": "test-finance"}).status_code == 403
        assert client.post("/api/reviewer/begin-review", json={"permit_id": pid}, headers={"X-Reviewer-Token": "test-reviewer"}).status_code == 200
        assert client.post("/api/inspection-proposal", json={"permit_id": pid.lower(), "slot": "2026-11-04T09:00:00"}).status_code == 200


def test_registration_required_and_ownership_rechecked(store):
    sid = store.new_session()
    args = Application(permit_type="FTR", district="Al-Rawdah")
    with pytest.raises(PermissionError):
        propose_application(store, sid, args)
    register(store, sid, Register(display_name="Demo", last4="4567", mobile="0501234567", consent=True))
    proposal = propose_application(store, sid, args)
    with pytest.raises(PermissionError):
        decide(store, store.new_session(), proposal["action_id"], True)
    assert not my_applications(store, sid)["applications"]


def test_case_insensitive_unicode_reference():
    assert Permit(permit_id=" ftr‑٣٠٣١١ ").permit_id == "FTR-30311"


async def test_model_cannot_claim_unconfirmed_booking_is_completed(store):
    sid = store.new_session()
    verify(store, sid, Verify(permit_id="FTR-30311", last4="6654", mobile="0532236654"))
    model = ScriptedModel([tool("book_inspection", {"permit_id": "FTR-30311", "slot": "2026-11-04T09:00:00"}),
                           answer("Your booking is confirmed and completed.")])
    result = await run_agent(store, sid, "Book an inspection", Settings(runtime=store.runtime, max_cost=10), model)
    assert "has not been executed" in result.reply
    assert "Your booking is confirmed" not in result.reply
    assert not permit_info(store, sid, "FTR-30311")["inspections"]


async def test_provider_authentication_failure_is_explained_without_secret(store):
    from rafeeq.agent import ProviderFailure

    class RejectedProvider:
        async def complete(self, messages, settings):
            raise ProviderFailure("invalid_key")

    result = await run_agent(store, store.new_session(), "permit fees", Settings(runtime=store.runtime), RejectedProvider())
    assert result.stopped == "provider_error"
    assert "401" in result.reply
    assert "Replace the key" in result.reply


@pytest.mark.parametrize("attendees,required", [(500, False), (501, True)])
def test_event_civil_defense_threshold(attendees, required):
    args = Application(permit_type="EVT", district="Al-Shati", event_days=2, attendees=attendees,
                       documents=["site_plan", "safety_plan"])
    assert ("civil_defense_review" in quote(args)["missing_documents"]) == required


def test_application_cannot_self_grant_fee_exemption():
    with pytest.raises(ValueError, match="officer"):
        quote(Application(permit_type="REN", district="Al-Shati", social_security=True))


def test_owned_application_details_hidden_when_verification_expires(store):
    sid = store.new_session()
    verify(store, sid, Verify(permit_id="FTR-30311", last4="6654", mobile="0532236654"))
    assert my_applications(store, sid)["applications"]
    with store.connect() as db:
        db.execute("UPDATE sessions SET verified_until=0 WHERE id=?", (sid,))
    assert my_applications(store, sid)["applications"] == []
    assert my_applications(store, sid)["verified_application"] is None
