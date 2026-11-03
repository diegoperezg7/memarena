"""Letta and Supermemory adapters against mock clients (no server, no key needed)."""

import sys
from types import SimpleNamespace

import pytest

from memarena.errors import MissingKeyError, OptionalDependencyError, ProviderUnreachableError
from memarena.systems import SystemConfig, build
from memarena.systems.letta_adapter import Letta
from memarena.systems.supermemory_adapter import Supermemory


class FakeSupermemory:
    def __init__(self):
        self.docs = []

    def add(self, namespace, content, date=None, metadata=None):
        self.docs.append(SimpleNamespace(namespace=namespace, content=content, metadata=metadata))

    def search(self, namespace, query, limit=10):
        words = set(query.lower().split())
        hits = [d for d in self.docs if d.namespace == namespace and words & set(d.content.lower().split())]
        return SimpleNamespace(
            results=[SimpleNamespace(memory=d.content, chunk=None, metadata=d.metadata) for d in hits[:limit]]
        )


def test_supermemory_roundtrip(history):
    fake = FakeSupermemory()
    s = Supermemory(SystemConfig(options={"supermemory_wait": 0}), client=fake)
    s.ingest(history)
    assert len(fake.docs) == 3 and fake.docs[0].metadata["date"] == "2023-05-01"
    got = s.retrieve("sister")
    assert "Denver" in got.context and "[2023-05-01]" in got.context
    assert s.remote == "supermemory"


def test_supermemory_needs_key(monkeypatch):
    monkeypatch.delenv("SUPERMEMORY_API_KEY", raising=False)
    with pytest.raises(MissingKeyError, match="SUPERMEMORY_API_KEY"):
        build("supermemory", SystemConfig())


class FakeLetta:
    def __init__(self, fail_connect=False):
        self.passages_store = []
        self.deleted = []
        self.fail_connect = fail_connect
        outer = self

        class Passages:
            def create(self, agent_id, text, tags=None, created_at=None):
                outer.passages_store.append((text, created_at))

            def search(self, agent_id, query, top_k=10):
                words = set(query.lower().split())
                hits = [(t, c) for t, c in outer.passages_store if words & set(t.lower().split())]
                return SimpleNamespace(
                    results=[SimpleNamespace(content=t, timestamp=c or "") for t, c in hits[:top_k]]
                )

        class Agents:
            passages = Passages()

            def create(self, **kw):
                if outer.fail_connect:
                    raise ConnectionError("connect refused")
                outer.created = kw
                return SimpleNamespace(id="agent-1")

            def delete(self, agent_id):
                outer.deleted.append(agent_id)

        self.agents = Agents()


def test_letta_archival_roundtrip(history, monkeypatch):
    monkeypatch.delenv("LETTA_API_KEY", raising=False)
    monkeypatch.delenv("LETTA_BASE_URL", raising=False)
    fake = FakeLetta()
    s = Letta(SystemConfig(), client=fake)
    s.ingest(history)
    assert fake.created["model"] == "ollama/qwen3:4b"
    assert fake.created["embedding"] == "ollama/nomic-embed-text:latest"
    assert fake.passages_store[0][1] == "2023-05-01T00:00:00Z"
    assert "Miso" in s.retrieve("cat named").context
    s.close()
    assert fake.deleted == ["agent-1"]


def test_letta_down_is_actionable(history, monkeypatch):
    monkeypatch.delenv("LETTA_API_KEY", raising=False)
    monkeypatch.delenv("LETTA_BASE_URL", raising=False)
    s = Letta(SystemConfig(), client=FakeLetta(fail_connect=True))
    with pytest.raises(ProviderUnreachableError, match="LETTA_API_KEY"):
        s.ingest(history)


def test_letta_cloud_defaults(monkeypatch):
    monkeypatch.setenv("LETTA_API_KEY", "x")
    monkeypatch.delenv("LETTA_BASE_URL", raising=False)
    s = Letta(SystemConfig(), client=FakeLetta())
    assert s.base_url == "https://api.letta.com" and s.remote == "letta"
    assert s._models() == ("openai/gpt-4o-mini", "openai/text-embedding-3-small")


def test_mem0_missing_extra_is_actionable(monkeypatch):
    monkeypatch.setitem(sys.modules, "mem0", None)
    with pytest.raises(OptionalDependencyError, match=r"memarena\[mem0\]"):
        build("mem0", SystemConfig())
