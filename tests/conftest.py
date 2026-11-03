from __future__ import annotations

import json
from pathlib import Path

import pytest

from memarena.llm import Budget, Usage
from memarena.models import History, Message, Question, QuestionSet, Session

FIXTURES = Path(__file__).parent / "fixtures"


class FakeLLM:
    """Stands in for memarena.llm.LLM: deterministic, no network, charges a fixed cost per call."""

    def __init__(self, reply, label="fake/model", cost=0.001, budget: Budget | None = None):
        self.reply = reply
        self.label = label
        self.cost = cost
        self.budget = budget or Budget(10)
        self.local = False
        self.calls: list[list[dict]] = []

    def chat(self, messages, max_tokens=512, temperature=0.0, json_mode=False):
        self.budget.check(self.cost)
        self.calls.append(messages)
        text = self.reply(messages) if callable(self.reply) else self.reply
        self.budget.add("fake", self.cost)
        return text, Usage(prompt_tokens=100, completion_tokens=10, cost=self.cost)


@pytest.fixture
def history() -> History:
    return History(
        [
            Session(
                "s1",
                [Message("user", "My sister Emily lives in Denver."), Message("assistant", "Nice city.")],
                "family",
                "2023-05-01T10:00:00",
            ),
            Session(
                "s2",
                [Message("user", "I adopted a cat named Miso."), Message("assistant", "Cute!")],
                "pets",
                "2023-05-03T10:00:00",
            ),
            Session(
                "s3",
                [
                    Message("user", "I now commute 45 minutes each way by train."),
                    Message("assistant", "That is a long commute."),
                ],
                "work",
                "2023-05-05T10:00:00",
            ),
        ]
    )


@pytest.fixture
def questions() -> QuestionSet:
    return QuestionSet(
        [
            Question(
                "q1",
                "single-session",
                "Where does my sister Emily live?",
                "Denver",
                status="approved",
                question_date="2023-05-10",
            ),
            Question("q2", "single-session", "What is my cat called?", "Miso", status="approved"),
            Question(
                "q3",
                "abstention",
                "What is my hamster called?",
                "The history does not say.",
                status="approved",
            ),
            Question("q4", "single-session", "Pending one", "x", status="pending"),
        ]
    )


def answer_from_context(messages):
    """Fake answer model: answers with the first known fact found in the context, else I don't know."""
    user = messages[-1]["content"]
    for fact in ("Denver", "Miso", "45 minutes"):
        if fact in user.split("Question:")[0] and fact.split()[0].lower() in _expected(user):
            return fact
    return "I don't know."


def _expected(user: str) -> str:
    q = user.split("Question:")[-1].lower()
    if "sister" in q:
        return "denver"
    if "cat" in q:
        return "miso"
    return ""


def judge_exact(messages):
    user = messages[-1]["content"]
    gold = user.split("Gold answer:")[1].split("\n")[0].strip()
    resp = user.split("Response to grade:")[1].split("\n")[0].strip()
    if "does not say" in gold:
        ok = "don't know" in resp.lower()
    else:
        ok = gold.lower() in resp.lower()
    return json.dumps({"correct": ok, "reason": "fake judge"})
