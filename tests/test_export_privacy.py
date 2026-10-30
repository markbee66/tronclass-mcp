import json
from dataclasses import asdict

from evaluation.run import run_cases
from tests.test_evaluation import FakeBackend
from tests.test_system1 import RecordingClient
from tronclass.config import Settings
from tronclass.contracts import AnswerRequest
from tronclass.export_privacy import connection_label
from tronclass.system1 import System1Assistant


def test_connection_label_has_no_host_or_path():
    assert connection_label("https://private-endpoint.invalid/v1") == "remote_https"
    assert connection_label("http://127.0.0.1:11434/v1") == "local_http"
    assert connection_label("") == "not_configured"


def test_conversation_result_does_not_export_endpoint_or_key(monkeypatch):
    endpoint = "https://private-endpoint.invalid/v1"
    monkeypatch.setenv("OLLAMA_API_KEY", "do-not-export-key")
    settings = Settings(base_url=endpoint, model="fixture")
    result = System1Assistant(settings, client=RecordingClient()).answer(
        AnswerRequest("fixture", settings.student_id, settings.reference_time))
    text = json.dumps(asdict(result))
    assert endpoint not in text and "private-endpoint" not in text and "do-not-export-key" not in text
    assert result.metadata["connection"] == "remote_https"


def test_evaluation_jsonl_and_csv_do_not_export_endpoint_or_private_paths(tmp_path):
    endpoint = "https://private-endpoint.invalid/v1"
    settings = Settings(base_url=endpoint, model="fixture", db_path=tmp_path / "private" / "course.db")
    target = tmp_path / "run.jsonl"
    run_cases(FakeBackend(), settings, [{"id":"fixture","question":"fixture"}], 1, target)
    for path in (target, target.with_suffix(".csv")):
        text = path.read_text(encoding="utf-8-sig")
        assert "private-endpoint" not in text and str(tmp_path) not in text
        assert "remote_https" in text


def test_evaluation_settings_use_only_file_names(tmp_path):
    settings = Settings(model="fixture", db_path=tmp_path / "private" / "course.db")
    target = tmp_path / "private-settings.jsonl"
    run_cases(FakeBackend(), settings, [{"id":"fixture","question":"fixture"}], 1, target)
    record = json.loads(target.read_text(encoding="utf-8"))
    assert record["settings"]["db_path"] == "course.db"
    assert record["settings"]["prompt_path"] == "system1.txt"
    assert "base_url" not in record["settings"]
