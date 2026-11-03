"""Plain data model shared by importers, generators, systems and the viewer."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

CATEGORIES = ["single-session", "multi-session", "temporal", "knowledge-update", "abstention"]


@dataclass
class Message:
    role: str  # "user" or "assistant"
    content: str
    timestamp: str | None = None  # ISO 8601


@dataclass
class Session:
    id: str
    messages: list[Message]
    title: str = ""
    started_at: str | None = None  # ISO 8601
    source: str = ""

    @property
    def date(self) -> str:
        return (self.started_at or "")[:10]


@dataclass
class Evidence:
    session_id: str
    message_index: int | None = None


@dataclass
class Question:
    id: str
    category: str
    question: str
    answer: str
    evidence: list[Evidence] = field(default_factory=list)
    question_date: str | None = None
    status: str = "pending"  # pending | approved | rejected
    source: str = "generated"
    note: str = ""


@dataclass
class History:
    sessions: list[Session]

    def to_json(self) -> dict:
        return {"version": 1, "sessions": [asdict(s) for s in self.sessions]}

    @classmethod
    def from_json(cls, data: dict) -> History:
        sessions = []
        for s in data.get("sessions", []):
            msgs = [Message(**m) for m in s.get("messages", [])]
            sessions.append(
                Session(
                    id=str(s["id"]),
                    messages=msgs,
                    title=s.get("title", ""),
                    started_at=s.get("started_at"),
                    source=s.get("source", ""),
                )
            )
        return cls(sessions)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_json(), ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> History:
        return cls.from_json(json.loads(Path(path).read_text(encoding="utf-8")))

    def by_id(self) -> dict[str, Session]:
        return {s.id: s for s in self.sessions}

    def sorted(self) -> list[Session]:
        return sorted(self.sessions, key=lambda s: (s.started_at or "", s.id))


@dataclass
class QuestionSet:
    questions: list[Question]
    meta: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"version": 1, "meta": self.meta, "questions": [asdict(q) for q in self.questions]}

    @classmethod
    def from_json(cls, data: dict) -> QuestionSet:
        qs = []
        for q in data.get("questions", []):
            q = dict(q)
            q["evidence"] = [Evidence(**e) for e in q.get("evidence", [])]
            qs.append(Question(**q))
        return cls(qs, data.get("meta", {}))

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_json(), ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> QuestionSet:
        return cls.from_json(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass
class Chunk:
    """A retrievable unit: one user turn plus the assistant reply that follows it."""

    session_id: str
    index: int
    date: str
    text: str


def chunk_history(history: History) -> list[Chunk]:
    chunks: list[Chunk] = []
    for s in history.sorted():
        i = 0
        msgs = s.messages
        while i < len(msgs):
            part = [msgs[i]]
            if msgs[i].role == "user" and i + 1 < len(msgs) and msgs[i + 1].role == "assistant":
                part.append(msgs[i + 1])
            text = "\n".join(f"{m.role}: {m.content}" for m in part)
            chunks.append(Chunk(s.id, i, s.date, text))
            i += len(part)
    return chunks


def format_session(s: Session) -> str:
    head = f"### Session {s.id} ({s.date or 'undated'})" + (f" - {s.title}" if s.title else "")
    body = "\n".join(f"{m.role}: {m.content}" for m in s.messages)
    return f"{head}\n{body}"
