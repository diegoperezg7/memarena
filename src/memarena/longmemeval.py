"""Convert LongMemEval (MIT, https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned) to memarena files.

Each LongMemEval question has its own haystack. memarena merges the haystacks of the selected questions
into ONE history, the way a single user's export looks, and asks every question against all of it.
"""

from __future__ import annotations

import random
import re

from .models import Evidence, History, Message, Question, QuestionSet, Session

TYPE_MAP = {
    "single-session-user": "single-session",
    "single-session-assistant": "single-session",
    "single-session-preference": "single-session",
    "multi-session": "multi-session",
    "temporal-reasoning": "temporal",
    "knowledge-update": "knowledge-update",
}

_DATE = re.compile(r"(\d{4})/(\d{2})/(\d{2})(?:\s*\(\w+\))?\s*(\d{2}):(\d{2})")


def to_iso(date: str | None) -> str | None:
    if not date:
        return None
    m = _DATE.search(date)
    if not m:
        return None
    y, mo, d, h, mi = m.groups()
    return f"{y}-{mo}-{d}T{h}:{mi}:00"


def category_of(item: dict) -> str:
    if str(item["question_id"]).endswith("_abs"):
        return "abstention"
    return TYPE_MAP.get(item["question_type"], "single-session")


def item_chars(item: dict) -> int:
    return sum(len(t["content"]) for s in item["haystack_sessions"] for t in s)


def select(
    items: list[dict],
    per_category: dict[str, int],
    seed: int = 7,
    max_chars: int = 20000,
    exclude_types: tuple[str, ...] = ("single-session-preference", "single-session-assistant"),
) -> list[dict]:
    """Seeded pick of questions per category, preferring small haystacks (under max_chars).

    Preference questions have rubric-style answers and assistant-recall questions test what the
    assistant said, not what the user said, so both are left out by default.
    """
    rng = random.Random(seed)
    pool = [i for i in items if i["question_type"] not in exclude_types]
    rng.shuffle(pool)
    chosen: list[dict] = []
    for cat, n in per_category.items():
        cands = [i for i in pool if category_of(i) == cat]
        small = [i for i in cands if item_chars(i) <= max_chars]
        rest = sorted((i for i in cands if item_chars(i) > max_chars), key=item_chars)
        chosen.extend((small + rest)[:n])
    return chosen


def convert(items: list[dict]) -> tuple[History, QuestionSet]:
    sessions: dict[str, Session] = {}
    questions = []
    for it in items:
        for sid, date, turns in zip(
            it["haystack_session_ids"], it["haystack_dates"], it["haystack_sessions"], strict=False
        ):
            if sid in sessions:
                continue
            iso = to_iso(date)
            msgs = [Message(t["role"], t["content"], iso) for t in turns if t.get("content")]
            sessions[sid] = Session(sid, msgs, "", iso, "longmemeval")
        evidence = []
        for sid, turns in zip(it["haystack_session_ids"], it["haystack_sessions"], strict=False):
            if sid not in it.get("answer_session_ids", []):
                continue
            idx = [i for i, t in enumerate(turns) if t.get("has_answer")]
            if idx:
                evidence.extend(Evidence(sid, i) for i in idx)
            else:
                evidence.append(Evidence(sid, None))
        qd = to_iso(it.get("question_date"))
        questions.append(
            Question(
                id=str(it["question_id"]),
                category=category_of(it),
                question=it["question"],
                answer=str(it["answer"]),
                evidence=evidence,
                question_date=qd[:10] if qd else None,
                status="approved",
                source="longmemeval",
                note=it["question_type"],
            )
        )
    return History(list(sessions.values())), QuestionSet(
        questions, {"source": "LongMemEval (MIT) xiaowu0162/longmemeval-cleaned"}
    )
