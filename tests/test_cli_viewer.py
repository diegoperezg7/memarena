import json
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

from typer.testing import CliRunner

from memarena.cli import app
from memarena.models import QuestionSet
from memarena.viewer import _Handler, export_site

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args, env=None):
    return subprocess.run(
        [sys.executable, "-m", "memarena.cli", *args], capture_output=True, text=True, env=env, cwd=ROOT
    )


def test_demo_prints_recorded_table():
    res = CliRunner().invoke(app, ["demo", "--no-view"], env={"COLUMNS": "200"})
    assert res.exit_code == 0, res.output
    assert "RECORDED RUN" in res.output
    for name in ("full-context", "bm25", "embeddings", "mem0"):
        assert name in res.output


def test_demo_data_is_real_and_complete():
    d = ROOT / "src" / "memarena" / "data" / "demo"
    r = json.loads((d / "results.json").read_text())
    assert r["meta"]["status"] == "complete" and r["meta"]["recorded"] is True
    assert len(r["answers"]) == len(r["questions"]) * len([s for s in r["systems"] if not s.get("error")])
    assert r["meta"]["dataset"]["license"] == "MIT"


def test_missing_key_error_has_no_traceback(tmp_path):
    import os

    env = {k: v for k, v in os.environ.items() if k != "MISTRAL_API_KEY"}
    (tmp_path / "h.json").write_text('{"sessions": []}')
    (tmp_path / "q.json").write_text('{"questions": []}')
    res = run_cli(
        "run",
        str(tmp_path / "h.json"),
        str(tmp_path / "q.json"),
        "--provider",
        "mistral",
        "--model",
        "ministral-8b-latest",
        env=env,
    )
    assert res.returncode == 1
    assert "MISTRAL_API_KEY" in res.stderr and "Traceback" not in res.stderr


def test_unknown_system_and_cloud_without_yes(tmp_path):
    (tmp_path / "h.json").write_text('{"sessions": []}')
    (tmp_path / "q.json").write_text('{"questions": []}')
    res = run_cli("run", str(tmp_path / "h.json"), str(tmp_path / "q.json"), "--systems", "zep")
    assert res.returncode == 1 and "Unknown system" in res.stderr and "Traceback" not in res.stderr
    import os

    env = dict(os.environ, MISTRAL_API_KEY="dummy")
    res = run_cli(
        "run",
        str(tmp_path / "h.json"),
        str(tmp_path / "q.json"),
        "--systems",
        "bm25",
        "--provider",
        "mistral",
        "--model",
        "ministral-8b-latest",
        env=env,
    )
    assert res.returncode == 1 and "Privacy warning" in res.stdout and "--yes" in res.stderr


def test_import_command(tmp_path):
    out = tmp_path / "h.json"
    res = CliRunner().invoke(
        app, ["import", str(ROOT / "tests/fixtures/chatgpt_conversations.json"), "--out", str(out)]
    )
    assert res.exit_code == 0 and "1 sessions" in res.output
    assert json.loads(out.read_text())["sessions"][0]["id"] == "c-1"


def test_export_site_and_question_saving(tmp_path, questions):
    qpath = tmp_path / "questions.json"
    questions.save(qpath)
    site = export_site(tmp_path / "site", None, qpath)
    assert (site / "index.html").exists()
    assert json.loads((site / "data/manifest.json").read_text()) == {"questions": "data/questions.json"}

    import socketserver
    from functools import partial

    handler = type("H", (_Handler,), {"questions_path": qpath})
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), partial(handler, directory=str(site)))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        ping = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping").read())
        assert ping == {"editable": True}
        data = questions.to_json()
        data["questions"][3]["status"] = "approved"
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/questions", data=json.dumps(data).encode(), method="PUT"
        )
        assert urllib.request.urlopen(req).status == 204
        assert QuestionSet.load(qpath).questions[3].status == "approved"
        live = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/data/questions.json").read())
        assert live["questions"][3]["status"] == "approved"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_judge_prompt_doc_is_in_sync():
    from memarena import prompts

    doc = (ROOT / "docs" / "judge-prompt.md").read_text()
    assert prompts.JUDGE_SYSTEM in doc and prompts.JUDGE_USER in doc
    assert prompts.ANSWER_USER in doc


def test_demo_table_fits_narrow_terminals():
    for cols in ("80", "120"):
        res = CliRunner().invoke(app, ["demo", "--no-view"], env={"COLUMNS": cols})
        assert res.exit_code == 0
        assert "…" not in res.output, f"truncated cells at {cols} columns"
        assert "full-context" in res.output and "accuracy by category" in res.output
        assert max(len(line) for line in res.output.splitlines()) <= int(cols)


def test_format_audit_handles_dict_and_string():
    from memarena.report import format_audit

    text = format_audit(
        {
            "checked": 80,
            "false_positives": {"bm25": 1},
            "false_negatives": {},
            "corrected_accuracy": {"bm25": 0.65},
        }
    )
    assert text.startswith("80 decisions checked by hand: 1 false positives (bm25 1), 0 false negatives.")
    assert "bm25 65%" in text
    assert format_audit("free text") == "free text"


def test_longmemeval_notice_ships_with_demo_data():
    from importlib import resources

    notice = resources.files("memarena") / "data" / "demo" / "LICENSE-LongMemEval.txt"
    text = notice.read_text()
    assert "Copyright (c) 2024 Di Wu" in text and "Permission is hereby granted" in text
