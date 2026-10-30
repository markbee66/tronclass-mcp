"""Model adapters. Credentials never enter public settings or result metadata."""

import json
import os
import socket
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from tronclass.config import Settings, cloudflare_token


class ModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    metadata: dict


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class HttpModelClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _request(self, path: str, payload=None, timeout=None, headers=None, base_url=None):
        base = self.settings.base_url if base_url is None else base_url
        if not base:
            raise ModelError("尚未設定模型服務。Cloudflare 模式請填入 CLOUDFLARE_ACCOUNT_ID。")
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            base.rstrip("/") + path,
            data=data,
            headers={"Content-Type": "application/json", **(headers or {})},
            method="GET" if payload is None else "POST",
        )
        try:
            with build_opener(NoRedirect()).open(request, timeout=timeout or self.settings.timeout_seconds) as response:
                body = json.load(response)
        except HTTPError as exc:
            # Do not echo request contents or a potentially sensitive server body.
            if self.settings.provider == "cloudflare":
                hints = {
                    401: "請確認 token 具有 Workers AI Read 權限及正確的帳戶範圍。",
                    403: "請確認此 token 的帳戶存取權與 Workers AI Read 權限。",
                    402: "請確認 Cloudflare Unified Billing 已啟用且有足夠 credits。",
                    404: "請確認帳戶、模型 ID 與 Cloudflare API 端點。",
                    429: "請稍後再試，並確認 Cloudflare 與模型的額度或頻率限制。",
                }
                hint = hints.get(exc.code, "請確認模型、帳戶權限與 Cloudflare 服務狀態。")
                raise ModelError(f"Cloudflare 回傳 HTTP {exc.code}。{hint}") from None
            if exc.code == 401:
                raise ModelError("模型服務回傳 HTTP 401，請確認 OLLAMA_API_KEY 與遠端閘道的金鑰設定。") from None
            raise ModelError(f"模型服務回傳 HTTP {exc.code}，請確認網址與模型名稱。") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise ModelError("模型回應逾時，請增加 LLM_TIMEOUT_SECONDS 或確認模型執行狀況。") from exc
        except (URLError, OSError) as exc:
            if self.settings.provider == "cloudflare":
                raise ModelError("無法連線 Cloudflare，請確認網路與服務網址。") from None
            raise ModelError("無法連線 Ollama。請先啟動 ollama serve，並確認服務網址。") from exc
        except (ValueError, UnicodeError) as exc:
            raise ModelError("模型服務回傳的內容不是有效的 JSON。") from exc
        if not isinstance(body, dict):
            raise ModelError("模型服務回傳格式錯誤。")
        return body


class OllamaClient(HttpModelClient):

    def _headers(self):
        # Keep the optional gateway credential out of Settings and result metadata.
        token = os.getenv("OLLAMA_API_KEY", "").strip()
        return {"Authorization": f"Bearer {token}"} if token else {}

    def list_models(self) -> list[str]:
        body = self._request("/models", timeout=min(self.settings.timeout_seconds, 5), headers=self._headers())
        models = body.get("data")
        if not isinstance(models, list) or any(not isinstance(m, dict) or not isinstance(m.get("id"), str) for m in models):
            raise ModelError("模型清單格式錯誤。")
        return sorted(m["id"] for m in models)

    def complete(self, messages: list[dict[str, str]]) -> Completion:
        if not self.settings.model.strip():
            raise ModelError("請填入 ollama list 顯示的完整模型名稱。")
        body = self._request("/chat/completions", {
            "model": self.settings.model,
            "messages": messages,
            "temperature": self.settings.temperature,
            "seed": self.settings.seed,
            "max_tokens": self.settings.max_tokens,
            "stream": False,
        }, headers=self._headers())
        try:
            choice = body["choices"][0]
            text = choice["message"]["content"]
            finish_reason = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelError("模型服務未回傳預期的 choices/message/content。") from exc
        if not isinstance(text, str) or not text.strip():
            raise ModelError("模型沒有回傳文字回答。")
        model = body.get("model", self.settings.model)
        if not isinstance(model, str):
            raise ModelError("模型名稱回傳格式錯誤。")
        return Completion(text=text, model=model, metadata={
            "response_id": body.get("id"),
            "system_fingerprint": body.get("system_fingerprint"),
            "usage": body.get("usage", {}),
            "finish_reason": finish_reason,
        })


class CloudflareClaudeClient(HttpModelClient):
    """Account REST API with Cloudflare Unified Billing; Anthropic Messages wire format."""

    def _headers(self):
        token = cloudflare_token()
        if not token:
            raise ModelError("請於本機 secrets.toml 或環境變數設定 CLOUDFLARE_API_TOKEN。")
        headers = {"Authorization": f"Bearer {token}", "cf-aig-skip-cache": "true"}
        if self.settings.cloudflare_gateway_id:
            headers["cf-aig-gateway-id"] = self.settings.cloudflare_gateway_id
        return headers

    def check_credentials(self):
        body = self._request("/user/tokens/verify", headers=self._headers(), timeout=10,
                             base_url="https://api.cloudflare.com/client/v4")
        result = body.get("result")
        if body.get("success") is not True or not isinstance(result, dict) or result.get("status") != "active":
            raise ModelError("Cloudflare 未確認 token 為 active。")
        return True

    def complete(self, messages: list[dict[str, str]]) -> Completion:
        if not self.settings.model:
            raise ModelError("請填入 Cloudflare Claude 模型 ID。")
        system = []
        conversation = []
        for message in messages:
            if message.get("role") == "system":
                system.append(message["content"])
            elif message.get("role") in {"user", "assistant"}:
                conversation.append({"role": message["role"], "content": message["content"]})
            else:
                raise ModelError("Claude 訊息只能包含 system、user 或 assistant。")
        payload = {
            "model": self.settings.model,
            "messages": conversation,
            "max_tokens": self.settings.max_tokens,
            "temperature": self.settings.temperature,
            "stream": False,
        }
        if system:
            payload["system"] = "\n\n".join(system)
        # Anthropic does not support seed; do not pretend it was applied.
        body = self._request("/messages", payload, headers=self._headers())
        content = body.get("content")
        if not isinstance(content, list) or any(not isinstance(block, dict) for block in content):
            raise ModelError("Claude 未回傳預期的 content 區塊。")
        texts = [block.get("text") for block in content if block.get("type") == "text"]
        if not texts or any(not isinstance(text, str) for text in texts) or not any(text.strip() for text in texts):
            raise ModelError("Claude 沒有回傳文字回答。")
        model = body.get("model", self.settings.model)
        if not isinstance(model, str):
            raise ModelError("Claude 回傳的模型名稱格式錯誤。")
        stop_reason = body.get("stop_reason")
        return Completion(text="\n".join(texts), model=model, metadata={
            "response_id": body.get("id"),
            "usage": body.get("usage", {}),
            "finish_reason": "length" if stop_reason == "max_tokens" else stop_reason,
            "stop_reason": stop_reason,
            "seed_applied": False,
            "skip_cache": True,
        })


def create_model_client(settings: Settings):
    if settings.provider == "cloudflare":
        return CloudflareClaudeClient(settings)
    return OllamaClient(settings)
