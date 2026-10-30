import csv
import json

import pytest

from evaluation.run import load_cases, main, run_cases
from tronclass.config import Settings
from tronclass.contracts import AnswerResult
from tronclass.llm import ModelError


class FakeBackend:
    def __init__(self):
        self.requests = []

    def answer(self, request):
        self.requests.append(request)
        if request.question == "故障測試":
            raise ModelError("模擬連線失敗")
        return AnswerResult("測試回答\n第二行", "fixture", 0.01, "data-hash", "prompt-hash")


def test_repetitions_are_isolated_and_errors_preserve_evidence_without_false_grading(tmp_path):
    backend = FakeBackend()
    cases = [{"id": "ok", "question": "正常測試", "expected": "人工標準答案"},
             {"id": "failure", "question": "故障測試"}]
    output = tmp_path / "results.jsonl"
    errors = run_cases(backend, Settings(model="fixture"), cases, 2, output)
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 4 and errors == 2
    assert all(request.history == [] for request in backend.requests)
    assert all(record["human_correct"] is None for record in records)
    assert records[0]["result"]["answer"] == "測試回答\n第二行"
    assert records[2]["result"] is None and records[2]["status"] == "error"
    with output.with_suffix(".csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 4 and rows[0]["human_correct"] == ""
    assert rows[0]["answer"] == "測試回答\n第二行"
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        run_cases(backend, Settings(model="fixture"), cases, 2, output)
    assert output.read_bytes() == before


def test_duplicate_case_ids_are_rejected(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([{"id": "same", "question": "a"}, {"id": "same", "question": "b"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="重複"):
        load_cases(path)


def test_dry_run_checks_real_data_without_model_service(monkeypatch, capsys):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    assert main(["--dry-run"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["cases"] == 3 and result["calls"] == 15
    assert len(result["context_sha256"]) == 64
