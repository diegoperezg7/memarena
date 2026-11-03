"""Turn chat exports into a memarena History.

Supported: ChatGPT export (conversations.json), Claude export (conversations.json) and generic JSONL.
"""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from .errors import MemarenaError
from .models import History, Message, Session


def _iso_from_epoch(ts) -> str | None:
    if ts in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _read_json_any(path: Path):
    """Read conversations.json directly or from inside an export .zip."""
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.endswith("conversations.json")]
            if not names:
                raise MemarenaError(f"{path} has no conversations.json inside.")
            return json.loads(z.read(names[0]).decode("utf-8"))
    return json.loads(path.read_text(encoding="utf-8"))


def _chatgpt_text(content: dict) -> str:
    parts = content.get("parts") or []
    texts = [p for p in parts if isinstance(p, str)]
    if not texts and isinstance(content.get("text"), str):
        texts = [content["text"]]
    return "\n".join(t for t in texts if t).strip()


def import_chatgpt(data) -> History:
    sessions = []
    for conv in data:
        mapping = conv.get("mapping") or {}
        node_id = conv.get("current_node")
        chain = []
        seen = set()
        while node_id and node_id in mapping and node_id not in seen:
            seen.add(node_id)
            chain.append(mapping[node_id])
            node_id = mapping[node_id].get("parent")
        if not chain:  # no current_node: fall back to creation order
            chain = sorted(mapping.values(), key=lambda n: (n.get("message") or {}).get("create_time") or 0)
        else:
            chain.reverse()
        msgs = []
        for node in chain:
            m = node.get("message") or {}
            role = (m.get("author") or {}).get("role")
            if role not in ("user", "assistant"):
                continue
            if (m.get("metadata") or {}).get("is_visually_hidden_from_conversation"):
                continue
            text = _chatgpt_text(m.get("content") or {})
            if text:
                msgs.append(Message(role, text, _iso_from_epoch(m.get("create_time"))))
        if msgs:
            sessions.append(
                Session(
                    id=str(conv.get("conversation_id") or conv.get("id") or f"chatgpt-{len(sessions)}"),
                    messages=msgs,
                    title=conv.get("title") or "",
                    started_at=_iso_from_epoch(conv.get("create_time")) or msgs[0].timestamp,
                    source="chatgpt",
                )
            )
    return History(sessions)


def import_claude(data) -> History:
    sessions = []
    for conv in data:
        msgs = []
        for m in conv.get("chat_messages") or []:
            role = {"human": "user", "assistant": "assistant"}.get(m.get("sender"))
            if not role:
                continue
            text = (m.get("text") or "").strip()
            if not text:
                text = "\n".join(
                    c.get("text", "") for c in (m.get("content") or []) if c.get("type") == "text"
                ).strip()
            if text:
                msgs.append(Message(role, text, m.get("created_at")))
        if msgs:
            sessions.append(
                Session(
                    id=str(conv.get("uuid") or f"claude-{len(sessions)}"),
                    messages=msgs,
                    title=conv.get("name") or "",
                    started_at=conv.get("created_at") or msgs[0].timestamp,
                    source="claude",
                )
            )
    return History(sessions)


def import_jsonl(text: str) -> History:
    """Each line is either a message ({session_id, role, content, timestamp?, title?})
    or a whole session ({id, messages: [...], title?, started_at?})."""
    sessions: dict[str, Session] = {}
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise MemarenaError(f"Line {n} is not valid JSON: {e.msg}") from e
        if "messages" in obj:
            sid = str(obj.get("id") or obj.get("session_id") or f"s{n}")
            msgs = [
                Message(m["role"], m["content"], m.get("timestamp"))
                for m in obj["messages"]
                if m.get("role") in ("user", "assistant") and m.get("content")
            ]
            sessions[sid] = Session(sid, msgs, obj.get("title", ""), obj.get("started_at"), "jsonl")
            continue
        if not {"role", "content"} <= obj.keys():
            raise MemarenaError(f"Line {n} needs 'role' and 'content' (and usually 'session_id').")
        if obj["role"] not in ("user", "assistant"):
            continue
        sid = str(obj.get("session_id", "default"))
        s = sessions.setdefault(sid, Session(sid, [], obj.get("title", ""), obj.get("timestamp"), "jsonl"))
        s.messages.append(Message(obj["role"], obj["content"], obj.get("timestamp")))
    return History([s for s in sessions.values() if s.messages])


def detect_format(path: Path) -> str:
    if path.suffix == ".jsonl":
        return "jsonl"
    data = _read_json_any(path)
    if isinstance(data, dict) and "sessions" in data:
        return "memarena"
    if isinstance(data, list) and data:
        first = data[0]
        if "mapping" in first:
            return "chatgpt"
        if "chat_messages" in first:
            return "claude"
    raise MemarenaError(f"Could not detect the format of {path}. Pass --format chatgpt, claude or jsonl.")


def load_any(path: Path, fmt: str = "auto") -> History:
    path = Path(path)
    if not path.exists():
        raise MemarenaError(f"File not found: {path}")
    if fmt == "auto":
        fmt = detect_format(path)
    if fmt == "jsonl":
        return import_jsonl(path.read_text(encoding="utf-8"))
    data = _read_json_any(path)
    if fmt == "memarena":
        return History.from_json(data)
    if fmt == "chatgpt":
        return import_chatgpt(data)
    if fmt == "claude":
        return import_claude(data)
    raise MemarenaError(f"Unknown format '{fmt}'.")
