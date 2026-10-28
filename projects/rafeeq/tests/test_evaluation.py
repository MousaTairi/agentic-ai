from __future__ import annotations

import json

import httpx
import pytest
from test_system import ScriptedModel, answer

from rafeeq import evaluate
from rafeeq.agent import OpenRouter, ProviderFailure, bridge, dispatch, run_agent
from rafeeq.config import Settings
from rafeeq.domain import verify
from rafeeq.evaluation_reporting import canonical_text, contains_expected, summary_for
from rafeeq.schemas import Reply, Verify
from rafeeq.scope import intent
from rafeeq.storage import Store


@pytest.mark.parametrize("citation", ["POL-02", "POL‑02", "POL‐02", "POL–02"])
def test_unicode_citation_normalization_without_relaxing_policy_number(citation):
    reply = Reply(reply="**335 SAR** (" + citation + ")", tools=["compute_fee"], actions=[],
                  stopped="completed", usage={}, trace_id="test")
    task = {"contains": [["335"], ["POL-02"]], "tools": ["compute_fee"]}
    assert evaluate.grade(task, reply, None, "") == []
    reply.reply = "335 SAR (POL-09)"
    assert evaluate.grade(task, reply, None, "") == ["answer_content"]


def test_numeric_grader_does_not_accept_7500_for_750():
    assert not contains_expected(canonical_text("7500 SAR (POL-02)"), "750")
    assert contains_expected(canonical_text("١٬٥٠٠ ريال (POL‑02)"), "1500")


def test_missing_citation_remains_a_failure():
    reply = Reply(reply="750 SAR", tools=["compute_fee"], actions=[], stopped="completed", usage={}, trace_id="x")
    assert evaluate.grade({"contains": [["750"], ["POL-02"]]}, reply, None, "") == ["answer_content"]


def test_provider_block_does_not_cascade_into_content_and_tool_failures():
    reply = Reply(reply="429", tools=[], actions=[], stopped="provider_error", error_code="rate_limit",
                  usage={}, trace_id="x")
    errors = evaluate.grade({"contains": [["750"]], "tools": ["compute_fee"], "action": "book_inspection"}, reply, None, "")
    assert errors == ["execution:provider_error"]


@pytest.mark.parametrize("message", ["ما حالة طلب اللوحة SGN-40220 وما آخر موعد للاعتراض؟",
                                    "Get my application status FTR-30311"])
def test_status_deadline_is_not_inspection_or_new_application(message):
    assert intent(message) == "policy"


async def test_verified_status_and_appeal_deadline_need_no_second_verification(tmp_path):
    store = Store(tmp_path)
    sid = store.new_session()
    verify(store, sid, Verify(permit_id="SGN-40220", last4="0093", mobile="0540410093"))
    model = ScriptedModel([answer("Please verify again.")])
    reply = await run_agent(store, sid, "ما حالة طلب اللوحة SGN-40220 وما آخر موعد للاعتراض؟",
                            Settings(runtime=tmp_path, max_cost=10), model)
    assert "مرفوض" in reply.reply and "2026-11-07" in reply.reply
    assert "get_permit" in reply.tools and not reply.ui_requests
    async with bridge(Settings(runtime=tmp_path)) as mcp:
        result = await dispatch("start_verification", '{"permit_id":"SGN‑40220"}', store, sid, mcp, "B")
    assert result["ok"] and "ui_request" not in result
    other = store.new_session()
    with pytest.raises(PermissionError):
        from rafeeq.domain import permit_info
        permit_info(store, other, "SGN-40220")


async def test_fixed_foodtruck_fee_computed_even_if_model_skips_tools(tmp_path):
    store = Store(tmp_path)
    reply = await run_agent(store, store.new_session(), "كم الرسوم السنوية لتصريح عربة طعام؟",
                            Settings(runtime=tmp_path, max_cost=10), ScriptedModel([answer("1500 ريال")]))
    assert "compute_fee" in reply.tools and "POL-02" in reply.reply
    assert any(event.get("data", {}).get("fee_sar") == 1500 for event in reply.tool_events)


async def test_rate_limit_stops_and_checkpoint_resumes_without_repeating_completed_tasks(tmp_path, monkeypatch):
    tasks = [{"id": "one", "category": "test", "prompt": "permit"}, {"id": "two", "category": "test", "prompt": "permit"}]
    calls = []

    async def blocked_agent(store, sid, prompt, settings, model):
        calls.append(settings.configuration)
        if len(calls) == 2:
            return Reply(reply="429", tools=[], actions=[], stopped="provider_error", error_code="rate_limit",
                         usage={}, trace_id="fixture")
        return Reply(reply="OK", tools=[], actions=[], stopped="completed", usage={"model_steps": 1}, trace_id="fixture")

    monkeypatch.setattr(evaluate, "run_agent", blocked_agent)
    output = tmp_path / "experiment"
    settings = Settings(model="fixture-model", api_key="")
    assert await evaluate.live(tasks, output, 1, settings=settings, provider=object()) == 2
    before = json.loads((output / "checkpoint.json").read_text(encoding="utf-8"))
    assert len(before) == 2
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert not summary["comparison"]["complete"]
    assert summary["B"]["blocked_provider"] == 1 and summary["B"]["failed_agent"] == 0

    async def ready_agent(store, sid, prompt, settings, model):
        calls.append(settings.configuration)
        return Reply(reply="OK", tools=[], actions=[], stopped="completed", usage={"model_steps": 1}, trace_id="fixture")

    monkeypatch.setattr(evaluate, "run_agent", ready_agent)
    assert await evaluate.live(tasks, output, 1, settings=settings, provider=object(), resume=True) == 0
    assert len(calls) == 5  # One blocked retry; the first completed A case is never repeated.
    after = json.loads((output / "checkpoint.json").read_text(encoding="utf-8"))
    assert len(after) == 5 and after[1]["row"]["outcome"] == "blocked_provider"
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["comparison"]["complete"] and summary["comparison"]["paired_model_task_runs"] == 2
    with pytest.raises(ValueError, match="different model"):
        await evaluate.live(tasks, output, 1, settings=settings.model_copy(update={"model": "changed"}),
                            provider=object(), resume=True)


async def test_429_is_not_retried_immediately(monkeypatch):
    hits = []
    transport = httpx.MockTransport(lambda request: (hits.append(request.url.path) or httpx.Response(429)))
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))
    with pytest.raises(ProviderFailure) as error:
        await OpenRouter().complete([], Settings(api_key="test-fixture"))
    assert error.value.code == "rate_limit" and len(hits) == 1


def test_incomplete_comparison_and_model_coverage_are_explicit():
    rows = [{"config": "A", "trial": 1, "task": "one", "passed": True, "errors": "", "outcome": "passed", "model_steps": 1},
            {"config": "B", "trial": 1, "task": "one", "passed": False, "errors": "execution:provider_error",
             "outcome": "blocked_provider", "model_steps": 0}]
    summary = summary_for(rows, 2)
    assert summary["B"]["blocked_provider"] == 1
    assert summary["B"]["unrun"] == 1 and summary["B"]["failed_agent"] == 0
    assert not summary["comparison"]["complete"] and summary["comparison"]["paired_model_task_runs"] == 0


async def test_invalid_booking_arguments_are_diagnosable_and_offer_slot_card(tmp_path):
    from test_system import tool

    store = Store(tmp_path)
    sid = store.new_session()
    verify(store, sid, Verify(permit_id="FTR-30311", last4="6654", mobile="0532236654"))
    model = ScriptedModel([tool("book_inspection", {"permit_id": "FTR-30311", "slot": "not a date"}), answer("")])
    reply = await run_agent(store, sid, "Book an inspection", Settings(runtime=tmp_path, max_cost=10), model)
    assert reply.stopped == "completed"
    assert any(request["type"] == "inspection_slots" for request in reply.ui_requests)
    event = next(event for event in reply.tool_events if event["name"] == "book_inspection")
    assert not event["ok"] and event["fields"][0]["field"] == "slot"
    assert "not a date" not in json.dumps(event)  # No raw arguments in diagnostic events.
