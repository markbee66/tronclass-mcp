"""python -m evaluation.run --cases evaluation/cases.example.json --repeat 5"""

import argparse
import csv
import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from tronclass.config import ROOT, Settings
from tronclass.contracts import AnswerRequest
from tronclass.database import CourseRepository, DataError, serialize_snapshot
from tronclass.factory import create_backend
from tronclass.fingerprints import sha256
from tronclass.llm import ModelError


def load_cases(path: Path):
    cases = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("測試題需為非空 JSON 陣列。")
    ids = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"].strip():
            raise ValueError("每題需提供非空的字串 id。")
        if not isinstance(case.get("question"), str) or not case["question"].strip():
            raise ValueError(f"{case['id']} 需提供非空問題。")
        if case["id"] in ids:
            raise ValueError(f"測試題 id 重複：{case['id']}")
        ids.add(case["id"])
        history = case.get("history", [])
        if not isinstance(history, list) or any(
            not isinstance(m, dict) or m.get("role") not in {"user", "assistant"}
            or not isinstance(m.get("content"), str) for m in history
        ):
            raise ValueError(f"{case['id']} 的 history 需為 user/assistant 文字訊息陣列。")
    return cases


def run_cases(backend, settings, cases, repeat, output: Path, input_fingerprints=None):
    """Flush each result immediately; never turn model/network errors into answers.

    Each repetition starts from the case's own history. Human grading is separate
    from execution status, so a successful HTTP response is never called correct.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid4())
    csv_path = output.with_suffix(".csv")
    if output.exists() or csv_path.exists():
        raise FileExistsError(f"輸出已存在，請指定新的檔名：{output} / {csv_path}")
    fields = ["run_id", "case_id", "repetition", "timestamp", "question", "expected", "category", "provider",
              "answer", "status", "error", "elapsed_seconds", "model", "requested_model", "temperature",
              "seed", "max_tokens", "base_url", "reference_time", "context_sha256", "prompt_sha256",
              "finish_reason", "human_correct", "review_notes"]
    failures = 0
    # Exclusive creation protects existing evidence from accidental overwrite.
    with output.open("x", encoding="utf-8") as log, csv_path.open("x", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            for repetition in range(1, repeat + 1):
                request = AnswerRequest(case["question"], settings.student_id, settings.reference_time,
                                        history=case.get("history", []))
                record = {
                    "run_id": run_id, "case_id": case["id"], "repetition": repetition,
                    "timestamp": datetime.now(timezone.utc).isoformat(), "case": case, "request": asdict(request),
                    "settings": {**asdict(settings), "db_path": str(settings.db_path), "prompt_path": str(settings.prompt_path)},
                    "human_correct": None, "review_notes": "", "status": "ok", "error": "", "result": None,
                    "initial_input_fingerprints": input_fingerprints or {},
                }
                started = time.perf_counter()
                try:
                    record["result"] = asdict(backend.answer(request))
                except (ModelError, DataError, ValueError, OSError) as exc:
                    record["status"] = "error"
                    record["error"] = str(exc)
                    failures += 1
                record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
                log.write(json.dumps(record, ensure_ascii=False) + "\n")
                log.flush()
                result = record["result"] or {}
                metadata = result.get("metadata", {})
                flat = {
                    **{k: record.get(k, "") for k in fields},
                    "question": case["question"], "expected": case.get("expected", ""),
                    "category": case.get("category", ""), "answer": result.get("answer", ""),
                    "model": result.get("model", ""), "requested_model": settings.model,
                    "provider": settings.provider,
                    "temperature": settings.temperature, "seed": settings.seed if settings.provider == "ollama" else None,
                    "max_tokens": settings.max_tokens,
                    "base_url": settings.base_url, "reference_time": settings.reference_time,
                    "context_sha256": result.get("context_sha256", ""),
                    "prompt_sha256": result.get("prompt_sha256", ""),
                    "finish_reason": metadata.get("finish_reason", ""),
                }
                writer.writerow(flat)
                csv_file.flush()
                print(f"{case['id']} {repetition}/{repeat}: {record['status']}", flush=True)
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the same System 1 entrypoint as Streamlit.")
    parser.add_argument("--cases", type=Path, default=ROOT / "evaluation" / "cases.example.json")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Validate cases/data/prompt without calling a model")
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat 必須大於零。")
    if args.output and args.output.suffix != ".jsonl":
        parser.error("--output 必須使用 .jsonl 副檔名。")
    try:
        settings = Settings.from_env()
        cases = load_cases(args.cases)
        hashes = {
            "context_sha256": sha256(serialize_snapshot(CourseRepository(settings.db_path).snapshot(settings.student_id))),
            "prompt_sha256": sha256(settings.prompt_path.read_text(encoding="utf-8")),
        }
        if args.dry_run:
            print(json.dumps({"cases": len(cases), "repeat": args.repeat,
                              "calls": len(cases) * args.repeat, **hashes}, ensure_ascii=False, indent=2))
            return 0
        if not settings.model:
            raise ValueError("請先設定 OLLAMA_MODEL 或 CLOUDFLARE_MODEL，指定所選服務的模型名稱。")
        output = args.output or ROOT / "results" / f"system1_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{uuid4().hex[:8]}.jsonl"
        failures = run_cases(create_backend(settings), settings, cases, args.repeat, output, hashes)
        print(f"Saved: {output}\nSaved: {output.with_suffix('.csv')}\nExecution errors: {failures}")
        return 1 if failures else 0
    except (DataError, ValueError, OSError) as exc:
        parser.exit(2, f"設定或輸出錯誤：{exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
