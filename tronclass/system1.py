"""Single LLM + basic prompt + full student-visible data. No MCP or verifier."""

import time

from tronclass.config import Settings
from tronclass.contracts import AnswerRequest, AnswerResult
from tronclass.database import CourseRepository, serialize_snapshot
from tronclass.fingerprints import sha256
from tronclass.llm import create_model_client


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

    def answer(self, request: AnswerRequest) -> AnswerResult:
        started = time.perf_counter()
        messages, hashes = self.build_messages(request)
        completion = self.client.complete(messages)
        return AnswerResult(
            answer=completion.text,
            model=completion.model,
            elapsed_seconds=round(time.perf_counter() - started, 3),
            **hashes,
            metadata={
                **completion.metadata,
                "backend": "system1",
                "provider": self.settings.provider,
                "requested_model": self.settings.model,
                "temperature": self.settings.temperature,
                "seed": self.settings.seed if self.settings.provider == "ollama" else None,
                "max_tokens": self.settings.max_tokens,
                "base_url": self.settings.base_url,
                "reference_time": request.reference_time,
                "student_id": request.student_id,
                "messages_sha256": sha256(serialize_snapshot({"messages": messages})),
                "context_characters": len(messages[0]["content"]),
            },
        )
