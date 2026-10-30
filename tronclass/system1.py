"""Single LLM + basic prompt + full student-visible data. No MCP or verifier.

A standalone greeting is the only exception: it gets a fixed reply without
reading course data or calling the model. Everything else keeps the full flow.
"""

import re
import time
import unicodedata

from tronclass.config import Settings
from tronclass.contracts import AnswerRequest, AnswerResult
from tronclass.database import CourseRepository, serialize_snapshot
from tronclass.fingerprints import sha256
from tronclass.export_privacy import connection_label
from tronclass.llm import create_model_client

# Exact words only: "你好嗎", "你好像…" or "hi there" are not in this set, so
# they and any mixed request reach the model. Extend only with tests.
GREETINGS = frozenset({
    "你好", "您好", "妳好", "你好呀", "你好啊", "您好呀", "嗨", "嗨嗨", "哈囉", "哈啰", "哈嘍",
    "安安", "早安", "午安", "晚安", "hello", "hi", "hey", "hiya",
})
SEPARATORS = re.compile(r"[\s,.!?~，。！？～、…]+")
GREETING_REPLY = (
    "你好！我是你的跨課程課業助理，可以查詢公告、作業截止時間、教材內容、成績與點名等課程資料。"
    "請直接告訴我想查什麼，例如「資料結構作業三什麼時候截止？」"
)


def is_pure_greeting(question: str, history=()) -> bool:
    """Conservative, deterministic check; no model is asked to classify.

    Only an opening message made entirely of greeting words qualifies. Any
    history means the turn may refer to earlier context, so it is not skipped.
    """
    if history or not isinstance(question, str) or len(question.strip()) > 20:
        return False
    words = [w for w in SEPARATORS.split(unicodedata.normalize("NFKC", question).casefold()) if w]
    return 0 < len(words) <= 3 and all(word in GREETINGS for word in words)


class System1Assistant:
    def __init__(self, settings: Settings, repository=None, client=None):
        self.settings = settings
        self.repository = repository or CourseRepository(settings.db_path)
        self.client = client or create_model_client(settings)

    def build_messages(self, request: AnswerRequest):
        if not request.question.strip():
            raise ValueError("問題不能為空白。")
        for message in request.history:
            if message.get("role") not in {"user", "assistant"} or not isinstance(message.get("content"), str):
                raise ValueError("對話歷史只能包含 user/assistant 文字訊息。")
        context = serialize_snapshot(self.repository.snapshot(request.student_id))
        prompt = self.settings.prompt_path.read_text(encoding="utf-8")
        system = (
            f"{prompt.strip()}\n\n目前學生：{request.student_id}"
            f"\n本次情境時間（固定參考時間）：{request.reference_time}"
            f"\n\n<course_data>\n{context}\n</course_data>"
        )
        messages = [{"role": "system", "content": system}]
        messages.extend({"role": m["role"], "content": m["content"]} for m in request.history)
        messages.append({"role": "user", "content": request.question})
        return messages, {"context_sha256": sha256(context), "prompt_sha256": sha256(prompt)}

    def _metadata(self, request: AnswerRequest):
        return {
            "backend": "system1",
            "provider": self.settings.provider,
            "requested_model": self.settings.model,
            "temperature": self.settings.temperature,
            "seed": self.settings.seed if self.settings.provider == "ollama" else None,
            "max_tokens": self.settings.max_tokens,
            "thinking": self.settings.thinking,
            "connection": connection_label(self.settings.base_url),
            "reference_time": request.reference_time,
            "student_id": request.student_id,
        }

    def answer(self, request: AnswerRequest) -> AnswerResult:
        started = time.perf_counter()
        if is_pure_greeting(request.question, request.history):
            total = time.perf_counter() - started
            return AnswerResult(
                answer=GREETING_REPLY, model="", elapsed_seconds=round(total, 3),
                context_sha256="", prompt_sha256="", verification="不適用（寒暄快速回覆，未呼叫模型）",
                metadata={
                    **self._metadata(request),
                    "route": "greeting", "model_called": False,
                    "usage": None, "finish_reason": None, "reasoning_characters": None,
                    "messages_sha256": None, "context_characters": 0,
                    "timing": {"preparation_seconds": round(total, 4), "model_request_seconds": None,
                               "total_seconds": round(total, 4)},
                },
            )
        messages, hashes = self.build_messages(request)
        prepared = time.perf_counter()
        completion = self.client.complete(messages)
        finished = time.perf_counter()
        return AnswerResult(
            answer=completion.text,
            model=completion.model,
            elapsed_seconds=round(finished - started, 3),
            **hashes,
            metadata={
                # Missing service fields stay unknown (None) instead of being invented.
                "usage": None, "finish_reason": None,
                **completion.metadata,
                **self._metadata(request),
                "route": "full", "model_called": True,
                "messages_sha256": sha256(serialize_snapshot({"messages": messages})),
                "context_characters": len(messages[0]["content"]),
                # The round trip includes queueing, model load, prompt processing,
                # any thinking and generation; the client cannot split these.
                "timing": {"preparation_seconds": round(prepared - started, 4),
                           "model_request_seconds": round(finished - prepared, 4),
                           "total_seconds": round(finished - started, 4)},
            },
        )
