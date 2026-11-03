from memarena.llm import Usage
from memarena.models import chunk_history
from memarena.systems import SystemConfig, build
from memarena.systems.baselines import Embeddings


def test_chunks_pair_user_and_assistant(history):
    chunks = chunk_history(history)
    assert len(chunks) == 3
    assert chunks[0].text.startswith("user: My sister") and "assistant: Nice city." in chunks[0].text


def test_bm25_finds_the_right_turn(history):
    s = build("bm25", SystemConfig(top_k=1))
    s.ingest(history)
    got = s.retrieve("Where does my sister live?")
    assert "Denver" in got.context and len(got.items) == 1
    assert "[2023-05-01]" in got.context


def test_bm25_no_match_returns_empty(history):
    s = build("bm25", SystemConfig(top_k=3))
    s.ingest(history)
    assert s.retrieve("zzzz qqqq").items == []


def test_full_context_keeps_newest_when_truncating(history):
    s = build("full-context", SystemConfig(max_context_tokens=30))
    s.ingest(history)
    got = s.retrieve("anything")
    assert got.truncated
    assert "commute" in got.context and "Emily" not in got.context
    s2 = build("full-context", SystemConfig())
    s2.ingest(history)
    full = s2.retrieve("x")
    assert not full.truncated and full.context.index("Emily") < full.context.index("commute")


class FakeEmbedder:
    local = True
    label = "fake/embed"
    provider = type("P", (), {"name": "fake"})()

    VOCAB = ["sister", "cat", "commute"]

    def embed(self, texts):
        vecs = [[1.0 if w in t.lower() else 0.0 for w in self.VOCAB] + [0.01] for t in texts]
        return vecs, Usage(prompt_tokens=len(texts))


def test_embeddings_cosine_search(history):
    s = Embeddings(SystemConfig(top_k=1, embed_model="other"), llm=FakeEmbedder())
    s.ingest(history)
    got = s.retrieve("how long is my commute")
    assert "45 minutes" in got.context
    assert s.usage.prompt_tokens == 4  # 3 chunks + 1 query
