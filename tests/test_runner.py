import json

import pytest

from memarena.errors import BudgetExceededError, MemarenaError
from memarena.llm import Budget
from memarena.models import QuestionSet
from memarena.runner import Runner
from memarena.systems import SystemConfig

from .conftest import FakeLLM, answer_from_context, judge_exact


def make_runner(history, questions, tmp_path, budget=None, systems=("full-context", "bm25"), **kw):
    budget = budget or Budget(5)
    return Runner(
        history,
        questions,
        list(systems),
        FakeLLM(answer_from_context, "fake/answer", budget=budget),
        FakeLLM(judge_exact, "fake/judge", budget=budget),
        SystemConfig(top_k=1),
        budget,
        tmp_path / "results.json",
        **kw,
    )


def test_end_to_end_with_fakes(history, questions, tmp_path):
    r = make_runner(history, questions, tmp_path)
    result = r.run()
    saved = json.loads((tmp_path / "results.json").read_text())
    assert saved["meta"]["status"] == "complete"
    assert len(saved["answers"]) == 6  # 2 systems x 3 approved questions (pending skipped)
    s = saved["summary"]["bm25"]
    assert s["n"] == 3 and s["correct"] == 3 and s["accuracy"] == 1.0
    assert s["by_category"]["abstention"]["accuracy"] == 1.0
    assert s["latency_p50_ms"] is not None and s["latency_p95_ms"] >= s["latency_p50_ms"]
    assert result["cost"]["total_usd"] == pytest.approx(12 * 0.001)
    assert saved["prompts"]["judge_user"].startswith("Question category")
    assert saved["meta"]["history"]["sessions"] == 3


def test_include_pending(history, questions, tmp_path):
    r = make_runner(history, questions, tmp_path, systems=("bm25",), include_pending=True)
    assert len(r.questions) == 4


def test_no_approved_questions_is_actionable(history, tmp_path):
    with pytest.raises(MemarenaError, match="memarena view"):
        make_runner(history, QuestionSet([]), tmp_path)


def test_budget_abort_keeps_partial_results(history, questions, tmp_path):
    budget = Budget(max_cost=0.0035)  # room for one question (answer + judge) and a bit
    r = make_runner(history, questions, tmp_path, budget=budget)
    with pytest.raises(BudgetExceededError):
        r.run()
    saved = json.loads((tmp_path / "results.json").read_text())
    assert saved["meta"]["status"] == "aborted"
    assert "Budget exceeded" in saved["meta"]["abort_reason"]
    assert 1 <= len(saved["answers"]) < 6
    assert saved["cost"]["total_usd"] <= 0.0035


def test_failing_system_does_not_kill_the_run(history, questions, tmp_path, monkeypatch):
    from memarena.systems import baselines

    def broken(self, h):
        raise RuntimeError("store exploded")

    monkeypatch.setattr(baselines.BM25, "ingest", broken)
    r = make_runner(history, questions, tmp_path)
    r.run()
    saved = json.loads((tmp_path / "results.json").read_text())
    errs = {s["name"]: s.get("error") for s in saved["systems"]}
    assert "store exploded" in errs["bm25"] and errs["full-context"] is None
    assert saved["summary"]["full-context"]["n"] == 3
