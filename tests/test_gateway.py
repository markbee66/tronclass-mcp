import json

import httpx
import pytest
from fastapi.testclient import TestClient
from tronclass.gateway import GatewayConfig, RequestBudget, create_gateway

KEY = "sk-" + "a" * 43
AUTH = {"Authorization": "Bearer " + KEY}


@pytest.fixture
def gateway():
    calls = []
    reply = {"status": 200, "body": {"choices": [{"message": {"content": "OK"}}]}}
    async def upstream(request):
        calls.append(request)
        return httpx.Response(reply["status"], json=reply["body"])
    app = create_gateway(GatewayConfig(api_key=KEY), transport=httpx.MockTransport(upstream))
    with TestClient(app) as client:
        yield client, calls, reply


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer old-key"}, {"Authorization": KEY}])
def test_gateway_rejects_missing_old_and_malformed_keys_before_upstream(gateway, headers):
    client, calls, _ = gateway
    assert client.get("/v1/models", headers=headers).status_code == 401
    assert not calls


def test_model_tools_context_and_output_settings_are_forwarded_without_extra_limits(gateway):
    client, calls, _ = gateway
    payload = {"model": "any-installed-model", "messages": [
        {"role": "assistant", "tool_calls": [{"id": "call1", "type": "function",
         "function": {"name": "query_courses", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call1", "content": "x" * 70000}],
        "tools": [{"type": "function", "function": {"name": "query_courses", "parameters": {}}}],
        "max_tokens": 16384, "reasoning_effort": "none", "stream": False}
    result = client.post("/v1/chat/completions", headers=AUTH, json=payload)
    assert result.status_code == 200
    assert json.loads(calls[0].content) == payload
    assert "authorization" not in calls[0].headers
    assert calls[0].url == "http://127.0.0.1:11434/v1/chat/completions"
    assert result.headers["cache-control"] == "no-store"


def test_model_list_is_forwarded_instead_of_restricting_models(gateway):
    client, calls, reply = gateway
    reply["body"] = {"data": [{"id": "model-a"}, {"id": "model-b"}]}
    response = client.get("/v1/models", headers=AUTH)
    assert response.json() == reply["body"]
    assert calls[0].url.path == "/v1/models"


@pytest.mark.parametrize("path", ["/api/pull", "/api/delete", "/api/create", "/docs", "/openapi.json", "/redoc", "/v1/embeddings"])
def test_management_and_unneeded_routes_are_absent(gateway, path):
    client, calls, _ = gateway
    assert client.get(path, headers=AUTH).status_code == 404
    assert not calls


def test_browser_origins_and_query_credentials_are_rejected(gateway):
    client, calls, _ = gateway
    assert client.get("/v1/models", headers={**AUTH, "Origin": "https://untrusted.invalid"}).status_code == 403
    assert client.get("/v1/models?api_key=secret", headers=AUTH).status_code == 404
    assert not calls


@pytest.mark.parametrize("status, expected", [(302, 502), (500, 500), (400, 400)])
def test_upstream_errors_and_redirects_do_not_echo_details(gateway, status, expected):
    client, calls, reply = gateway
    reply.update(status=status, body={"error": "private-host.invalid " + KEY})
    response = client.post("/v1/chat/completions", headers=AUTH, json={"model": "any"})
    assert response.status_code == expected
    assert len(calls) == 1
    assert "private-host" not in response.text and KEY not in response.text


def test_only_frequency_is_limited_and_window_recovers():
    now = [0.0]
    budget = RequestBudget(GatewayConfig(api_key=KEY, per_minute=2), lambda: now[0])
    assert budget.begin() is None
    assert budget.begin() is None
    assert budget.begin() == 429
    now[0] = 60
    assert budget.begin() is None
    assert budget.begin() is None


def test_http_rate_limit_returns_retry_after_without_an_upstream_call():
    now, calls = [0.0], []
    async def upstream(request):
        calls.append(request)
        return httpx.Response(200, json={"data": []})
    app = create_gateway(GatewayConfig(api_key=KEY, per_minute=1),
        transport=httpx.MockTransport(upstream), clock=lambda: now[0])
    with TestClient(app) as client:
        assert client.get("/v1/models", headers=AUTH).status_code == 200
        response = client.get("/v1/models", headers=AUTH)
        assert response.status_code == 429 and int(response.headers["retry-after"]) > 0
        assert len(calls) == 1
        now[0] = 60
        assert client.get("/v1/models", headers=AUTH).status_code == 200


def test_sse_can_pass_the_gateway_without_rewriting_tool_events():
    event = b'data: {"choices":[{"delta":{"tool_calls":[]}}]}\n\ndata: [DONE]\n\n'
    async def upstream(request):
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, headers={"content-type":"text/event-stream"}, content=event)
    app = create_gateway(GatewayConfig(api_key=KEY), transport=httpx.MockTransport(upstream))
    with TestClient(app) as client:
        response = client.post("/v1/chat/completions", headers=AUTH, json={"stream":True})
        assert response.content == event


def test_gateway_refuses_missing_or_weak_server_key():
    with pytest.raises(ValueError):
        create_gateway(GatewayConfig(api_key="weak"))
