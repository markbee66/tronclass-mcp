"""Manual latency comparison: python -m evaluation.latency --thinking default off

Runs the same System 1 entrypoint as Streamlit for four fixed scenarios and
prints one JSON line per run. Only timings, token counts and sizes are printed;
no endpoint, key, answer text or course data. Every model request counts toward
the shared gateway limit, so keep --repeat small on the remote service.

--native is a loopback-only diagnostic. It sends the same messages to Ollama's
native /api/chat instead of /v1 to read load/prompt/eval durations, which /v1
does not report. It replaces (not adds to) the /v1 request, because a second
request would reuse the prompt cache and understate prompt processing. It is
never used by the app and the public gateway does not expose that route.

Scenarios run in order and share the course-data prefix, so later requests may
reuse Ollama's prompt cache while the model stays loaded. Compare like with like.
"""

import argparse
import json
import sys
import time
from dataclasses import replace
from urllib.parse import urlparse
from urllib.request import Request, build_opener

from tronclass.config import THINKING_MODES, Settings
from tronclass.contracts import AnswerRequest
from tronclass.database import DataError
from tronclass.factory import create_backend
from tronclass.llm import ModelError, NoRedirect
from tronclass.system1 import is_pure_greeting

SCENARIOS = {
    "greeting": ("你好", []),
    "single_course": ("資料結構作業三（二元搜尋樹）最後的截止時間是什麼？請指出依據。", []),
    "cross_course": ("請依已公布的成績與配分，計算我每一科目前的加權成績，並列出尚未公布的項目。", []),
    "follow_up": ("那統計學作業三呢？兩者哪個比較早截止？", [
        {"role": "user", "content": "資料結構作業三什麼時候截止？"},
        {"role": "assistant", "content": "（先前回答，內容省略）"},
    ]),
}
NATIVE_THINK = {"default": None, "off": False, "on": True}
NATIVE_FIELDS = ("load_duration", "prompt_eval_count", "prompt_eval_duration", "eval_count", "eval_duration",
                 "total_duration")


def is_loopback(base_url):
    return urlparse(base_url).hostname in {"localhost", "127.0.0.1", "::1"}


def native_durations(settings, messages, timeout):
    """Loopback only: native Ollama reports nanosecond durations. Missing stays None."""
    if not is_loopback(settings.base_url):
        raise ValueError("--native 只允許本機 Ollama（localhost／loopback）。")
    root = settings.base_url.rstrip("/").removesuffix("/v1")
    payload = {"model": settings.model, "messages": messages, "stream": False,
               "options": {"temperature": settings.temperature, "seed": settings.seed}}
    if NATIVE_THINK[settings.thinking] is not None:
        payload["think"] = NATIVE_THINK[settings.thinking]
    request = Request(root + "/api/chat", json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                      {"Content-Type": "application/json"})
    with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
        body = json.load(response)
    result = {}
    for field in NATIVE_FIELDS:
        value = body.get(field)
        result[field] = (value / 1e9 if field.endswith("duration") else value) if isinstance(value, int) else None
    thinking = (body.get("message") or {}).get("thinking")
    result["thinking_characters"] = len(thinking) if isinstance(thinking, str) else None
    return result


def measure(backend, settings, scenario, native=False):
    question, history = SCENARIOS[scenario]
    request = AnswerRequest(question, settings.student_id, settings.reference_time, history=list(history))
    row = {"scenario": scenario, "thinking": settings.thinking, "status": "ok",
           "api": "native" if native and not is_pure_greeting(question, history) else "v1"}
    started = time.perf_counter()
    if row["api"] == "native":
        return {**row, **measure_native(backend, settings, request, started)}
    try:
        result = backend.answer(request)
    except (ModelError, DataError, ValueError, OSError) as exc:
        # ModelError text is written to be shareable; other errors may contain local paths.
        error = str(exc) if isinstance(exc, ModelError) else type(exc).__name__
        return {**row, "status": "error", "error": error,
                "client_seconds": round(time.perf_counter() - started, 3)}
    meta = result.metadata
    usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
    row.update({
        "route": meta.get("route"), "model_called": meta.get("model_called"),
        **(meta.get("timing") or {}),
        "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
        "reasoning_characters": meta.get("reasoning_characters"), "finish_reason": meta.get("finish_reason"),
        "context_characters": meta.get("context_characters"), "answer_characters": len(result.answer),
    })
    return row


def measure_native(backend, settings, request, started):
    messages, _ = backend.build_messages(request)
    prepared = time.perf_counter()
    try:
        durations = native_durations(settings, messages, settings.timeout_seconds)
    except (OSError, ValueError) as exc:
        return {"status": "error", "error": type(exc).__name__}
    finished = time.perf_counter()
    return {"route": "full", "model_called": True, "preparation_seconds": round(prepared - started, 4),
            "model_request_seconds": round(finished - prepared, 4), "total_seconds": round(finished - started, 4),
            "context_characters": len(messages[0]["content"]), **durations}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare System 1 latency by scenario and thinking mode.")
    parser.add_argument("--thinking", nargs="+", choices=THINKING_MODES, default=["default"])
    parser.add_argument("--scenarios", nargs="+", choices=list(SCENARIOS), default=list(SCENARIOS))
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--native", action="store_true", help="本機診斷：另以原生 /api/chat 讀取各階段耗時")
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat 必須大於零。")
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        base = Settings.from_env()
        if not base.model:
            raise ValueError("請先設定 OLLAMA_MODEL。")
        if args.native and not is_loopback(base.base_url):
            raise ValueError("--native 只允許本機 Ollama（localhost／loopback）。")
        if base.provider != "ollama" and args.thinking != ["default"]:
            raise ValueError("思考模式比較只適用於 Ollama。")
    except (ValueError, OSError) as exc:
        parser.exit(2, f"設定錯誤：{exc}\n")
    for mode in args.thinking:
        settings = replace(base, thinking=mode)
        backend = create_backend(settings)
        for repetition in range(1, args.repeat + 1):
            for scenario in args.scenarios:
                row = measure(backend, settings, scenario, args.native)
                print(json.dumps({"repetition": repetition, **row}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
