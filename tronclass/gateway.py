"""Authenticated, rate-limited forwarding to loopback Ollama. No model policy."""
import os
import secrets
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

UPSTREAM = "http://127.0.0.1:11434"
SAFE_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer"}


@dataclass(frozen=True)
class GatewayConfig:
    api_key: str = field(repr=False)
    per_minute: int = 30


class RequestBudget:
    """Sliding-window requests per minute; one worker owns this shared budget."""
    def __init__(self, config, clock=time.monotonic):
        self.config, self.clock, self.requests = config, clock, deque()

    def begin(self):
        now = self.clock()
        while self.requests and now - self.requests[0] >= 60:
            self.requests.popleft()
        if len(self.requests) >= self.config.per_minute:
            return 429
        self.requests.append(now)

    def retry_after(self):
        return max(1, int(60 - (self.clock() - self.requests[0])) + 1) if self.requests else 1


def error(status, message, retry_after=None):
    headers = {**SAFE_HEADERS}
    if retry_after:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse({"error": {"message": message}}, status_code=status, headers=headers)


def create_gateway(config=None, *, transport=None, clock=time.monotonic):
    if config is None:
        key_file = os.environ.get("TRONCLASS_API_KEY_FILE", "")
        if not key_file:
            raise ValueError("TRONCLASS_API_KEY_FILE must point to a private key file.")
        config = GatewayConfig(api_key=Path(key_file).read_text(encoding="utf-8").strip(),
                               per_minute=int(os.environ.get("TRONCLASS_API_RPM", "30")))
    if len(config.api_key) < 40 or not config.api_key.isascii():
        raise ValueError("A strong ASCII API key is required.")
    if config.per_minute < 1:
        raise ValueError("Requests per minute must be positive.")
    budget = RequestBudget(config, clock)
    client = httpx.AsyncClient(transport=transport, trust_env=False, follow_redirects=False,
                               timeout=httpx.Timeout(None, connect=5.0))

    @asynccontextmanager
    async def lifespan(app):
        yield
        await client.aclose()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.middleware("http")
    async def boundary(request, call_next):
        supplied = request.headers.get("authorization", "")
        if not supplied.isascii() or not secrets.compare_digest(supplied, "Bearer " + config.api_key):
            return error(401, "Unauthorized")
        if request.headers.get("origin"):
            return error(403, "Browser-origin requests are not supported.")
        if request.url.query or (request.method, request.url.path) not in {
            ("GET", "/v1/models"), ("POST", "/v1/chat/completions")
        }:
            return error(404, "Not found")
        if budget.begin():
            return error(429, "Request rate exceeded; retry later.", budget.retry_after())
        response = await call_next(request)
        response.headers.update(SAFE_HEADERS)
        return response

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        return error(500, "Internal gateway error")

    async def forward(request: Request):
        # Destination and headers are server-owned; never forward the team's key.
        body = await request.body() if request.method == "POST" else None
        outgoing = client.build_request(request.method, UPSTREAM + request.url.path, content=body,
                                         headers={"Content-Type": "application/json"})
        try:
            upstream = await client.send(outgoing, stream=True)
        except httpx.HTTPError:
            return error(502, "Local model connection failed.")
        if upstream.status_code != 200:
            status = upstream.status_code
            await upstream.aclose()
            return error(status if 400 <= status < 600 else 502, "Local model request failed.")

        async def response_body():
            try:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            except httpx.HTTPError:
                # End a failed stream without exposing origin details or payloads.
                return
            finally:
                await upstream.aclose()

        return StreamingResponse(response_body(), headers={**SAFE_HEADERS,
            "Content-Type": upstream.headers.get("content-type", "application/json")})

    app.add_api_route("/v1/models", forward, methods=["GET"])
    app.add_api_route("/v1/chat/completions", forward, methods=["POST"])
    return app
