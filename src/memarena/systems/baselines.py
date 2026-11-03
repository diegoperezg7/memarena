"""Baselines every run includes: the whole history pasted in, BM25 and embedding search."""

from __future__ import annotations

import math
import re
from collections import Counter

from ..llm import LLM, approx_tokens
from ..models import History, chunk_history, format_session
from .base import MemorySystem, Retrieved, render_items


class FullContext(MemorySystem):
    """Paste the whole history (newest kept if it does not fit in max_context_tokens)."""

    name = "full-context"
    kind = "baseline"

    def ingest(self, history: History) -> None:
        self.blocks = [format_session(s) for s in history.sorted()]

    def retrieve(self, question, question_date=None) -> Retrieved:
        budget = self.config.max_context_tokens
        kept: list[str] = []
        used = 0
        for block in reversed(self.blocks):
            t = approx_tokens(block)
            if used + t > budget:
                break
            kept.append(block)
            used += t
        kept.reverse()
        return Retrieved("\n\n".join(kept), [], truncated=len(kept) < len(self.blocks))

    def describe(self) -> str:
        return f"full-context (max ~{self.config.max_context_tokens} tokens)"


_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = set(
    "a an the and or of to in on at for is are was were be been it this that i you my me we our your "
    "do did does what which who when where how with as by from have has had can could would should".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


class BM25(MemorySystem):
    """Okapi BM25 over turn pairs (user message + assistant reply). No dependencies, no network."""

    name = "bm25"
    kind = "baseline"
    k1 = 1.5
    b = 0.75

    def ingest(self, history: History) -> None:
        self.chunks = chunk_history(history)
        self.docs = [Counter(tokenize(c.text)) for c in self.chunks]
        self.lens = [sum(d.values()) for d in self.docs]
        self.avgdl = (sum(self.lens) / len(self.lens)) if self.lens else 0.0
        df: Counter = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        q = tokenize(query)
        out = []
        for d, dl in zip(self.docs, self.lens, strict=True):
            s = 0.0
            for t in q:
                f = d.get(t)
                if not f:
                    continue
                s += (
                    self.idf[t]
                    * f
                    * (self.k1 + 1)
                    / (f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
                )
            out.append(s)
        return out

    def retrieve(self, question, question_date=None) -> Retrieved:
        sc = self.scores(question)
        top = sorted(range(len(sc)), key=lambda i: -sc[i])[: self.config.top_k]
        top = [i for i in top if sc[i] > 0]
        items = [(self.chunks[i].date, self.chunks[i].text) for i in top]
        return Retrieved(render_items(items), [self.chunks[i].text for i in top])

    def describe(self) -> str:
        return f"bm25 (top {self.config.top_k} turns)"


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class Embeddings(MemorySystem):
    """Cosine search over embedded turn pairs (simple RAG)."""

    name = "embeddings"
    kind = "baseline"
    max_chars = 2000  # keep each chunk inside small embedding models' context

    def __init__(self, config, budget=None, llm: LLM | None = None) -> None:
        super().__init__(config, budget)
        self.llm = llm or LLM(config.embed_provider, config.embed_model, budget=budget)
        self.remote = None if self.llm.local else self.llm.provider.name
        self._nomic = "nomic" in config.embed_model

    def _doc(self, t: str) -> str:
        t = t[: self.max_chars]
        return f"search_document: {t}" if self._nomic else t

    def _query(self, t: str) -> str:
        return f"search_query: {t}" if self._nomic else t

    def ingest(self, history: History) -> None:
        self.chunks = chunk_history(history)
        texts = [self._doc(f"[{c.date}] {c.text}") for c in self.chunks]
        self.vectors, u = self.llm.embed(texts) if texts else ([], None)
        if u:
            self._add_usage(u)

    def retrieve(self, question, question_date=None) -> Retrieved:
        (qv,), u = self.llm.embed([self._query(question)])
        self._add_usage(u)
        sc = [_cos(qv, v) for v in self.vectors]
        top = sorted(range(len(sc)), key=lambda i: -sc[i])[: self.config.top_k]
        items = [(self.chunks[i].date, self.chunks[i].text) for i in top]
        return Retrieved(render_items(items), [self.chunks[i].text for i in top])

    def describe(self) -> str:
        return f"embeddings ({self.llm.label}, top {self.config.top_k} turns)"
