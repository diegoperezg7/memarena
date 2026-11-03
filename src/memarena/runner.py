"""Run a benchmark: ingest the history into every system, ask every question, judge every answer."""

from __future__ import annotations

import json
import os
import platform
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .errors import BudgetExceededError, MemarenaError
from .judge import judge
from .llm import LLM, Budget, approx_tokens
from .metrics import summarize
from .models import CATEGORIES, History, QuestionSet
from .prompts import ANSWER_SYSTEM, ANSWER_USER, JUDGE_SYSTEM, JUDGE_USER
from .systems import SystemConfig, build


def hardware() -> str:
    mem = ""
    try:
        if hasattr(os, "sysconf"):
            mem = f", {round(os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 2**30)} GB RAM"
    except (ValueError, OSError):
        pass
    return f"{platform.system()} {platform.machine()}, {os.cpu_count()} CPUs{mem}"


def history_stats(history: History) -> dict:
    msgs = sum(len(s.messages) for s in history.sessions)
    chars = sum(len(m.content) for s in history.sessions for m in s.messages)
    dates = sorted(s.date for s in history.sessions if s.date)
    return {
        "sessions": len(history.sessions),
        "messages": msgs,
        "approx_tokens": chars // 4,
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
    }


class Runner:
    def __init__(
        self,
        history: History,
        questions: QuestionSet,
        system_names: list[str],
        answer_llm: LLM,
        judge_llm: LLM,
        sys_config: SystemConfig,
        budget: Budget,
        out_path: Path,
        include_pending: bool = False,
        dataset_info: dict | None = None,
        progress=None,
    ) -> None:
        self.history = history
        allowed = {"approved"} | ({"pending"} if include_pending else set())
        self.questions = [q for q in questions.questions if q.status in allowed]
        if not self.questions:
            raise MemarenaError(
                "No approved questions to run. Review them first with 'memarena view --questions FILE' "
                "(or pass --include-pending to use unreviewed ones)."
            )
        self.system_names = system_names
        self.answer_llm = answer_llm
        self.judge_llm = judge_llm
        self.sys_config = sys_config
        self.budget = budget
        self.out_path = Path(out_path)
        self.progress = progress or (lambda msg: None)
        self.result: dict = {
            "meta": {
                "tool": "memarena",
                "version": __version__,
                "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "hardware": hardware(),
                "answer_model": answer_llm.label,
                "judge_model": judge_llm.label,
                "embed_model": f"{sys_config.embed_provider}/{sys_config.embed_model}",
                "memory_llm": f"{sys_config.llm_provider}/{sys_config.llm_model}",
                "top_k": sys_config.top_k,
                "max_context_tokens": sys_config.max_context_tokens,
                "history": history_stats(history),
                "dataset": dataset_info or {},
                "max_cost": budget.max_cost,
                "status": "running",
            },
            "prompts": {
                "answer_system": ANSWER_SYSTEM,
                "answer_user": ANSWER_USER,
                "judge_system": JUDGE_SYSTEM,
                "judge_user": JUDGE_USER,
            },
            "categories": CATEGORIES,
            "systems": [],
            "questions": [asdict(q) for q in self.questions],
            "answers": [],
            "summary": {},
            "cost": {},
        }

    def save(self) -> None:
        r = self.result
        r["summary"] = summarize(r["answers"], r["systems"], CATEGORIES)
        r["cost"] = {"total_usd": round(self.budget.spent, 6), "by_provider": self.budget.by_provider}
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.out_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.out_path)

    def answer(self, context: str, q) -> tuple[str, object]:
        user = ANSWER_USER.format(
            context=context or "(empty)", question=q.question, question_date=q.question_date or "unknown"
        )
        return self.answer_llm.chat(
            [{"role": "system", "content": ANSWER_SYSTEM}, {"role": "user", "content": user}], max_tokens=200
        )

    def run(self) -> dict:
        # Build every system first so missing keys, servers or extras fail before anything is spent.
        systems = [build(n, self.sys_config, self.budget) for n in self.system_names]
        try:
            for sysm in systems:
                self._run_system(sysm)
            self.result["meta"]["status"] = "complete"
        except BudgetExceededError as e:
            self.result["meta"]["status"] = "aborted"
            self.result["meta"]["abort_reason"] = str(e)
            raise
        except KeyboardInterrupt:
            self.result["meta"]["status"] = "aborted"
            self.result["meta"]["abort_reason"] = "interrupted"
            raise
        finally:
            for s in systems:
                s.close()
            self.save()
        return self.result

    def _run_system(self, sysm) -> None:
        entry = {"name": sysm.name, "kind": sysm.kind, "description": sysm.describe()}
        self.result["systems"].append(entry)
        self.progress(f"[{sysm.name}] ingesting {len(self.history.sessions)} sessions")
        sysm.progress = self.progress
        t0 = time.perf_counter()
        try:
            sysm.ingest(self.history)
        except (BudgetExceededError, KeyboardInterrupt):
            raise
        except MemarenaError as e:
            entry["error"] = str(e)
            self.progress(f"[{sysm.name}] failed: {e}")
            return
        except Exception as e:  # a third-party system crashing must not kill the other results
            entry["error"] = f"{type(e).__name__}: {e}"[:500]
            self.progress(f"[{sysm.name}] failed: {entry['error']}")
            return
        entry["ingest_seconds"] = round(time.perf_counter() - t0, 3)
        entry["ingest_tokens"] = sysm.usage.prompt_tokens + sysm.usage.completion_tokens
        entry["ingest_cost"] = round(sysm.usage.cost, 6)
        self.save()
        for i, q in enumerate(self.questions, 1):
            before = sysm.usage.cost
            t1 = time.perf_counter()
            try:
                got = sysm.retrieve(q.question, q.question_date)
            except (BudgetExceededError, KeyboardInterrupt):
                raise
            except Exception as e:
                entry["error"] = f"retrieve failed: {type(e).__name__}: {e}"[:500]
                self.progress(f"[{sysm.name}] {entry['error']}")
                return
            retrieval_ms = (time.perf_counter() - t1) * 1000
            response, usage = self.answer(got.context, q)
            correct, reason, jusage = judge(self.judge_llm, q.category, q.question, q.answer, response)
            self.result["answers"].append(
                {
                    "system": sysm.name,
                    "question_id": q.id,
                    "category": q.category,
                    "response": response,
                    "correct": correct,
                    "judge_reason": reason,
                    "retrieval_ms": round(retrieval_ms, 2),
                    "context_tokens_approx": approx_tokens(got.context),
                    "truncated": got.truncated,
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "answer_cost": round(usage.cost, 6),
                    "retrieval_cost": round(sysm.usage.cost - before, 6),
                    "judge_cost": round(jusage.cost, 6),
                    "retrieved": [t[:600] for t in got.items[:10]],
                }
            )
            mark = "ok " if correct else "no "
            self.progress(f"[{sysm.name}] {i}/{len(self.questions)} {mark} {q.id}")
            self.save()
