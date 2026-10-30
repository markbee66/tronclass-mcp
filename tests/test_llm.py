import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tronclass.config import Settings
from tronclass.llm import CloudflareClaudeClient, ModelError, OllamaClient


@pytest.fixture
def model_server():
    state = {"requests": [], "headers": [], "status": 200, "body": {
        "model": "fixture-model", "choices": [{"message": {"content": "測試回答"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 123, "completion_tokens": 10},
    }}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["headers"].append(dict(self.headers))
            state["requests"].append((self.path, None))
            self.respond({"data": [{"id": "fixture-model"}]})

        def do_POST(self):
            state["headers"].append(dict(self.headers))
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append((self.path, body))
            self.respond(state["body"])

        def respond(self, body):
            encoded = json.dumps(body).encode()
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            if state["status"] == 302:
                self.send_header("Location", "/credential-leak-target")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_openai_compatible_ollama_wire_format_and_generation_settings(model_server):
    url, state = model_server
    client = OllamaClient(Settings(base_url=url, model="fixture-model"))
    assert client.list_models() == ["fixture-model"]
    messages = [{"role": "user", "content": "中文問題"}]
    result = client.complete(messages)
    assert state["requests"][0][0] == "/v1/models"
    path, body = state["requests"][1]
    assert path == "/v1/chat/completions"
    assert body == {"model": "fixture-model", "messages": messages, "temperature": 0,
                    "seed": 42, "max_tokens": 2048, "stream": False}
    assert result.text == "測試回答"
    assert result.metadata["usage"]["prompt_tokens"] == 123


@pytest.mark.parametrize("body", [{}, {"choices": []}, {"choices": [{"message": {"content": ""}}]}])
def test_malformed_model_response_is_an_error_not_an_answer(model_server, body):
    url, state = model_server
    state["body"] = body
    with pytest.raises(ModelError):
        OllamaClient(Settings(base_url=url, model="fixture-model")).complete([])


def test_http_failure_reports_actionable_error(model_server):
    url, state = model_server
    state["status"] = 404
    with pytest.raises(ModelError, match="HTTP 404"):
        OllamaClient(Settings(base_url=url, model="missing-model")).complete([])


def test_cloudflare_messages_format_authentication_and_seed_not_sent(model_server, monkeypatch):
    url, state = model_server
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "fake-cloudflare-token")
    state["body"] = {
        "id": "msg_fixture", "model": "claude-fixture-pinned", "stop_reason": "max_tokens",
        "content": [{"type": "thinking", "thinking": "hidden reasoning"},
                    {"type": "text", "text": "第一段"}, {"type": "text", "text": "第二段"}],
        "usage": {"input_tokens": 120, "output_tokens": 10},
    }
    settings = Settings(provider="cloudflare", base_url=url, model="anthropic/fixture", cloudflare_gateway_id="team-gateway")
    result = CloudflareClaudeClient(settings).complete([
        {"role": "system", "content": "課程資料"}, {"role": "user", "content": "中文問題"},
    ])
    path, payload = state["requests"][0]
    assert path == "/v1/messages"
    assert payload["system"] == "課程資料"
    assert payload["messages"] == [{"role": "user", "content": "中文問題"}]
    assert "seed" not in payload
    headers = {key.lower(): value for key, value in state["headers"][0].items()}
    assert headers["authorization"] == "Bearer fake-cloudflare-token"
    assert headers["cf-aig-skip-cache"] == "true"
    assert headers["cf-aig-gateway-id"] == "team-gateway"
    assert result.text == "第一段\n第二段"
    assert result.model == "claude-fixture-pinned"
    assert result.metadata["finish_reason"] == "length"
    assert result.metadata["seed_applied"] is False
    assert "fake-cloudflare-token" not in json.dumps(result.metadata)


def test_cloudflare_billing_error_does_not_echo_response_secrets(model_server, monkeypatch):
    url, state = model_server
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "fake-cloudflare-token")
    state["status"] = 402
    state["body"] = {"error": "do-not-log-this-body"}
    with pytest.raises(ModelError, match="402.*credits") as error:
        CloudflareClaudeClient(Settings(provider="cloudflare", base_url=url, model="anthropic/fixture")).complete([])
    assert "fake-cloudflare-token" not in str(error.value)
    assert "do-not-log-this-body" not in str(error.value)


def test_cloudflare_redirect_is_not_followed_with_credentials(model_server, monkeypatch):
    url, state = model_server
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "fake-cloudflare-token")
    state["status"] = 302
    with pytest.raises(ModelError, match="302"):
        CloudflareClaudeClient(Settings(provider="cloudflare", base_url=url, model="anthropic/fixture")).complete([])
    assert len(state["requests"]) == 1


def test_missing_cloudflare_token_fails_before_network_request(model_server):
    url, state = model_server
    with pytest.raises(ModelError, match="CLOUDFLARE_API_TOKEN"):
        CloudflareClaudeClient(Settings(provider="cloudflare", base_url=url, model="anthropic/fixture")).complete([])
    assert not state["requests"]
