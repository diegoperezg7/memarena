import json
import zipfile

import pytest

from memarena.errors import MemarenaError
from memarena.importers import detect_format, import_jsonl, load_any

from .conftest import FIXTURES


def test_chatgpt_follows_current_branch_and_skips_system():
    h = load_any(FIXTURES / "chatgpt_conversations.json")
    assert len(h.sessions) == 1  # the empty conversation is dropped
    s = h.sessions[0]
    assert s.id == "c-1" and s.title == "Trip planning" and s.source == "chatgpt"
    assert [m.role for m in s.messages] == ["user", "assistant", "user"]
    assert "regenerated" not in " ".join(m.content for m in s.messages)
    assert s.messages[2].content == "I fly there on June 3."  # non-text parts ignored
    assert s.started_at.startswith("2023-05-20")


def test_claude_export_uses_content_blocks_when_text_empty():
    h = load_any(FIXTURES / "claude_conversations.json")
    s = h.sessions[0]
    assert s.title == "Running plan"
    assert s.messages[1].content == "Congratulations on the 5K!"
    assert s.date == "2023-03-19"


def test_jsonl_both_shapes():
    h = load_any(FIXTURES / "generic.jsonl")
    ids = {s.id: s for s in h.sessions}
    assert set(ids) == {"a", "c"}  # b only had a system message
    assert ids["a"].messages[0].content.startswith("I adopted")
    assert ids["c"].title == "Work"


def test_jsonl_bad_line_has_clear_error():
    with pytest.raises(MemarenaError, match="Line 1"):
        import_jsonl("{not json}\n")
    with pytest.raises(MemarenaError, match="role"):
        import_jsonl('{"session_id": "x"}\n')


def test_detect_and_zip(tmp_path):
    z = tmp_path / "export.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.write(FIXTURES / "claude_conversations.json", "data/conversations.json")
    assert detect_format(z) == "claude"
    assert load_any(z).sessions[0].id == "k-1"


def test_unknown_format(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps([{"foo": 1}]))
    with pytest.raises(MemarenaError, match="--format"):
        load_any(p)
    with pytest.raises(MemarenaError, match="not found"):
        load_any(tmp_path / "missing.json")
