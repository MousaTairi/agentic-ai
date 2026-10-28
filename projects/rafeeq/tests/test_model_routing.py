from __future__ import annotations

import json

import httpx
import pytest

from rafeeq.agent import OpenRouter, ProviderFailure, run_agent
from rafeeq.config import Settings
from rafeeq.storage import Store


def mock_client(monkeypatch, handler):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs))


@pytest.mark.parametrize("status", [404, 429, 500, 502, 503, 504])
async def test_chat_uses_only_named_backup_after_primary_failure(monkeypatch, status):
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(status)
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    mock_client(monkeypatch, handler)
    response = await OpenRouter().complete([], Settings(api_key="fixture", model="vendor/primary",
                                                       fallback_model="vendor/backup"))
    assert [body["model"] for body in requests] == ["vendor/primary", "vendor/backup"]
    assert all(body["tools"] and body["provider"]["require_parameters"] for body in requests)
    assert response["rafeeq_selected_model"] == "vendor/backup"


@pytest.mark.parametrize("status,code", [(401, "invalid_key"), (402, "credits"), (403, "access_denied")])
async def test_account_errors_never_switch_models(monkeypatch, status, code):
    requests = []
    mock_client(monkeypatch, lambda request: requests.append(request) or httpx.Response(status))
    with pytest.raises(ProviderFailure) as error:
        await OpenRouter().complete([], Settings(api_key="fixture", fallback_model="vendor/backup"))
    assert error.value.code == code and len(requests) == 1


@pytest.mark.parametrize("error_type,code", [(httpx.ConnectError, "provider_connection"),
                                            (httpx.ReadTimeout, "provider_timeout")])
async def test_transport_failure_is_specific_and_never_echoes_raw_exception(monkeypatch, error_type, code):
    def handler(request):
        raise error_type("secret-sentinel", request=request)

    mock_client(monkeypatch, handler)
    with pytest.raises(ProviderFailure) as error:
        await OpenRouter().complete([], Settings(api_key="fixture"))
    assert error.value.code == code and "secret-sentinel" not in str(error.value)


async def test_fallback_failure_stops_at_two_requests(monkeypatch):
    requests = []
    mock_client(monkeypatch, lambda request: requests.append(request) or httpx.Response(429))
    with pytest.raises(ProviderFailure, match="rate_limit"):
        await OpenRouter().complete([], Settings(api_key="fixture", fallback_model="vendor/backup"))
    assert len(requests) == 2


async def test_transport_failure_can_use_explicit_backup(monkeypatch):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content)["model"])
        if len(requests) == 1:
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    mock_client(monkeypatch, handler)
    await OpenRouter().complete([], Settings(api_key="fixture", model="vendor/primary", fallback_model="vendor/backup"))
    assert requests == ["vendor/primary", "vendor/backup"]


def test_backup_cannot_be_an_automatic_router():
    with pytest.raises(ValueError, match="specific model"):
        Settings(fallback_model="openrouter/free")


async def test_connection_error_reply_does_not_blame_key(tmp_path, monkeypatch):
    class Offline:
        async def complete(self, messages, settings):
            raise ProviderFailure("provider_connection")

    store = Store(tmp_path)
    reply = await run_agent(store, store.new_session(), "What is the signage fee?",
                            Settings(runtime=tmp_path, max_cost=10), Offline())
    assert reply.error_code == "provider_connection"
    assert "could not connect" in reply.reply and "Check the server API key" not in reply.reply
