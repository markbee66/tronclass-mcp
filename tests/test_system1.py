from tronclass.config import Settings
from tronclass.contracts import AnswerRequest
from tronclass.llm import Completion
from tronclass.system1 import System1Assistant


class RecordingClient:
    def __init__(self):
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        return Completion("模型原始回答", "test-model", {"finish_reason": "stop"})


def test_baseline_calls_one_model_with_full_visible_data_and_preserves_raw_answer():
    settings = Settings(model="test-model")
    client = RecordingClient()
    assistant = System1Assistant(settings, client=client)
    history = [{"role": "user", "content": "先問資料結構"}, {"role": "assistant", "content": "好的"}]
    request = AnswerRequest("作業三何時截止？", settings.student_id, settings.reference_time, history)
    result = assistant.answer(request)
    assert len(client.calls) == 1
    messages = client.calls[0]
    assert messages[1:3] == history
    assert messages[-1] == {"role": "user", "content": request.question}
    assert all(course in messages[0]["content"] for course in ("C01", "C02", "C03", "C04"))
    assert "2026-11-06 23:59" in messages[0]["content"]
    assert "12:00" in messages[0]["content"]
    assert result.answer == "模型原始回答"
    assert result.tool_calls == [] and result.sources == []
    assert "未驗證" in result.verification
    assert len(result.context_sha256) == 64
    assert request.history == history


def test_same_snapshot_prompt_and_question_have_same_fingerprint():
    settings = Settings(model="test-model")
    assistant = System1Assistant(settings, client=RecordingClient())
    request = AnswerRequest("測試", settings.student_id, settings.reference_time)
    first = assistant.answer(request)
    second = assistant.answer(request)
    assert first.context_sha256 == second.context_sha256
    assert first.prompt_sha256 == second.prompt_sha256
    assert first.metadata["messages_sha256"] == second.metadata["messages_sha256"]


def test_cloudflare_result_does_not_claim_seed_was_applied():
    settings = Settings(provider="cloudflare", model="anthropic/fixture", base_url="")
    assistant = System1Assistant(settings, client=RecordingClient())
    result = assistant.answer(AnswerRequest("測試", settings.student_id, settings.reference_time))
    assert result.metadata["provider"] == "cloudflare"
    assert result.metadata["seed"] is None
