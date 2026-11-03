import json

from memarena.longmemeval import convert, select, to_iso
from memarena.models import CATEGORIES
from memarena.qa import generate, validate

from .conftest import FIXTURES, FakeLLM


def test_generate_marks_pending_and_validates_evidence(history):
    def reply(messages):
        prompt = messages[-1]["content"]
        sid = prompt.split('Session id="')[1].split('"')[0]
        if "NEVER stated" in prompt:
            return json.dumps(
                {
                    "question": "What is my hamster called?",
                    "answer": "The history does not say.",
                    "evidence": [],
                }
            )
        if "AT LEAST TWO" in prompt:
            ids = [p.split('"')[0] for p in prompt.split('Session id="')[1:]]
            return json.dumps(
                {
                    "question": "Q?",
                    "answer": "A",
                    "evidence": [{"session_id": i, "message_index": 0} for i in ids],
                }
            )
        return json.dumps(
            {"question": "Q?", "answer": "A", "evidence": [{"session_id": sid, "message_index": 0}]}
        )

    qs = generate(history, FakeLLM(reply), per_category=1)
    assert {q.category for q in qs.questions} == set(CATEGORIES)
    assert all(q.status == "pending" for q in qs.questions)
    assert all(q.question_date == "2023-05-05" for q in qs.questions)
    multi = [q for q in qs.questions if q.category == "multi-session"][0]
    assert len({e.session_id for e in multi.evidence}) >= 2


def test_validate_rejects_bad_output(history):
    group = history.sessions[:1]
    assert validate({"skip": True}, group, "single-session") is None
    assert (
        validate(
            {"question": "q", "answer": "a", "evidence": [{"session_id": "nope"}]}, group, "single-session"
        )
        is None
    )
    ok = validate(
        {"question": "q", "answer": "a", "evidence": [{"session_id": "s1", "message_index": 99}]},
        group,
        "single-session",
    )
    assert ok and ok[2][0].message_index is None
    assert (
        validate(
            {"question": "q", "answer": "a", "evidence": [{"session_id": "s1", "message_index": 0}]},
            group,
            "multi-session",
        )
        is None
    )


def test_longmemeval_convert_merges_haystacks():
    items = json.loads((FIXTURES / "longmemeval_mini.json").read_text())
    chosen = select(items, {c: 5 for c in CATEGORIES})
    assert "q4" not in {i["question_id"] for i in chosen}  # preference questions excluded
    h, qs = convert(chosen)
    assert sorted(s.id for s in h.sessions) == ["s1", "s2", "s3"]
    cats = {q.id: q.category for q in qs.questions}
    assert cats == {"q1": "single-session", "q2_abs": "abstention", "q3": "knowledge-update"}
    q1 = [q for q in qs.questions if q.id == "q1"][0]
    assert q1.evidence[0].message_index == 0 and q1.question_date == "2023-05-22"
    assert all(q.status == "approved" for q in qs.questions)
    assert to_iso("2023/05/20 (Sat) 02:21") == "2023-05-20T02:21:00"
