"""Stable boundary for the UI, evaluation runner and future System 2 coordinator."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class AnswerRequest:
    question: str
    student_id: str
    reference_time: str
    history: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    model: str
    elapsed_seconds: float
    context_sha256: str
    prompt_sha256: str
    verification: str = "未驗證（System 1）"
    tool_calls: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class AssistantBackend(Protocol):
    def answer(self, request: AnswerRequest) -> AnswerResult: ...
