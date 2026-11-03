"""Generate benchmark questions from a history with an LLM, in LongMemEval's five categories.

Generated questions start as status "pending". Review them in the viewer before running: an unreviewed
question set makes the benchmark unreliable.
"""

from __future__ import annotations

import random

from .judge import parse_json_object
from .llm import LLM
from .models import CATEGORIES, Evidence, History, Question, QuestionSet, Session
from .prompts import QA_INSTRUCTIONS, QA_SYSTEM, QA_USER
from .systems.baselines import tokenize

MAX_MSG_CHARS = 700
MAX_SESSION_CHARS = 9000


def render_for_qa(s: Session) -> str:
    lines = [f'Session id="{s.id}" date={s.date or "unknown"} title="{s.title}"']
    used = 0
    for i, m in enumerate(s.messages):
        text = m.content if m.role == "user" else m.content[:MAX_MSG_CHARS]
        line = f"[{i}] {m.role}: {text}"
        used += len(line)
        if used > MAX_SESSION_CHARS:
            lines.append("[...] (rest of session omitted)")
            break
        lines.append(line)
    return "\n".join(lines)


def _user_terms(s: Session) -> set[str]:
    return set(tokenize(" ".join(m.content for m in s.messages if m.role == "user")))


def _most_similar(target: Session, pool: list[Session], k: int) -> list[Session]:
    t = _user_terms(target)
    scored = []
    for s in pool:
        if s.id == target.id:
            continue
        u = _user_terms(s)
        scored.append((len(t & u) / (len(t | u) or 1), s))
    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:k]]


def pick_sessions(category: str, sessions: list[Session], rng: random.Random) -> list[Session]:
    anchor = rng.choice(sessions)
    if category in ("single-session", "abstention") or len(sessions) < 2:
        return [anchor]
    if category == "multi-session":
        group = [anchor, *_most_similar(anchor, sessions, 2)]
    else:  # temporal, knowledge-update: two related sessions on different dates
        others = [s for s in _most_similar(anchor, sessions, 5) if s.date != anchor.date] or _most_similar(
            anchor, sessions, 1
        )
        group = [anchor, others[0]]
    return sorted(group, key=lambda s: s.started_at or "")


def validate(obj: dict | None, group: list[Session], category: str) -> tuple[str, str, list[Evidence]] | None:
    if not obj or obj.get("skip") or not obj.get("question") or not obj.get("answer"):
        return None
    ids = {s.id: s for s in group}
    evidence = []
    for e in obj.get("evidence") or []:
        if not isinstance(e, dict) or str(e.get("session_id")) not in ids:
            continue
        idx = e.get("message_index")
        sess = ids[str(e["session_id"])]
        if isinstance(idx, int) and 0 <= idx < len(sess.messages):
            evidence.append(Evidence(sess.id, idx))
        else:
            evidence.append(Evidence(sess.id, None))
    if category != "abstention" and not evidence:
        return None
    if category == "multi-session" and len({e.session_id for e in evidence}) < 2:
        return None
    return str(obj["question"]).strip(), str(obj["answer"]).strip(), evidence


def generate(
    history: History,
    llm: LLM,
    per_category: int = 4,
    categories: list[str] | None = None,
    seed: int = 7,
    progress=None,
) -> QuestionSet:
    progress = progress or (lambda m: None)
    rng = random.Random(seed)
    sessions = [s for s in history.sorted() if any(m.role == "user" for m in s.messages)]
    if not sessions:
        raise ValueError("The history has no user messages.")
    dates = [s.date for s in sessions if s.date]
    qdate = max(dates) if dates else None
    questions: list[Question] = []
    for cat in categories or CATEGORIES:
        made = 0
        for _attempt in range(per_category * 3):
            if made >= per_category:
                break
            group = pick_sessions(cat, sessions, rng)
            prompt = QA_USER.format(
                instructions=QA_INSTRUCTIONS[cat], sessions="\n\n".join(render_for_qa(s) for s in group)
            )
            text, _ = llm.chat(
                [{"role": "system", "content": QA_SYSTEM}, {"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.3,
                json_mode=True,
            )
            ok = validate(parse_json_object(text), group, cat)
            if not ok:
                continue
            q, a, ev = ok
            made += 1
            questions.append(Question(f"{cat}-{made}", cat, q, a, ev, qdate, "pending", "generated"))
            progress(f"{cat}: {made}/{per_category}")
    return QuestionSet(questions, {"generator": llm.label, "seed": seed})
