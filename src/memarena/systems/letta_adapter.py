"""Letta adapter over Letta's REST API (letta-client 1.12.1). Install with: uv tool install 'memarena[letta]'.

Targets Letta Cloud (set LETTA_API_KEY) or any self-hosted server that still exposes the /v1 REST API
(set LETTA_BASE_URL). Note: since 0.34 the letta/letta Docker image and the `letta` PyPI package ship
"Letta Code" and no longer the Python REST server, so a fresh `docker run letta/letta` will not work.

v0.1 writes every turn into the agent's archival memory and retrieves with Letta's archival search.
It does not drive the agent loop (that would make the agent's own LLM the thing under test).
"""

from __future__ import annotations

import os
import uuid

from ..errors import OptionalDependencyError, ProviderUnreachableError
from ..models import History, chunk_history
from .base import MemorySystem, Retrieved, render_items

CLOUD_URL = "https://api.letta.com"


def letta_base_url() -> str:
    url = os.environ.get("LETTA_BASE_URL", "").strip()
    if url:
        return url.rstrip("/")
    return CLOUD_URL if os.environ.get("LETTA_API_KEY") else "http://localhost:8283"


class Letta(MemorySystem):
    name = "letta"
    kind = "memory"

    def __init__(self, config, budget=None, client=None) -> None:
        super().__init__(config, budget)
        self.base_url = letta_base_url()
        self.cloud = self.base_url.startswith(CLOUD_URL)
        if client is None:
            try:
                from letta_client import Letta as LettaClient
            except ImportError as e:
                raise OptionalDependencyError(
                    "letta-client is not installed. Install the extra: uv tool install 'memarena[letta]'."
                ) from e
            client = LettaClient(base_url=self.base_url, api_key=os.environ.get("LETTA_API_KEY") or None)
        self.client = client
        local_host = any(h in self.base_url for h in ("localhost", "127.0.0.1"))
        self.remote = None if local_host else "letta"
        self.agent_id: str | None = None

    def _models(self) -> tuple[str, str]:
        o = self.config.options
        if self.cloud:
            return o.get("letta_model") or "openai/gpt-4o-mini", o.get("letta_embedding") or (
                "openai/text-embedding-3-small"
            )
        model = o.get("letta_model") or f"{self.config.llm_provider}/{self.config.llm_model}"
        emb = o.get("letta_embedding") or f"{self.config.embed_provider}/{self.config.embed_model}"
        if self.config.embed_provider == "ollama" and ":" not in emb.split("/", 1)[1]:
            emb += ":latest"
        return model, emb

    def ingest(self, history: History) -> None:
        model, embedding = self._models()
        try:
            agent = self.client.agents.create(
                name=f"memarena-{uuid.uuid4().hex[:8]}",
                model=model,
                embedding=embedding,
                memory_blocks=[{"label": "human", "value": "The user whose history is being tested."}],
            )
        except Exception as e:
            if "connect" in str(e).lower() or "Connect" in type(e).__name__:
                raise ProviderUnreachableError(
                    f"Letta is not reachable at {self.base_url}. Set LETTA_API_KEY for Letta Cloud, or "
                    "LETTA_BASE_URL to a self-hosted Letta server that exposes the REST API."
                ) from e
            raise
        self.agent_id = agent.id
        for c in chunk_history(history):
            kw = {"text": f"[{c.date}] {c.text}", "tags": [c.session_id]}
            if c.date:
                kw["created_at"] = c.date + "T00:00:00Z"
            self.client.agents.passages.create(self.agent_id, **kw)

    def retrieve(self, question, question_date=None) -> Retrieved:
        res = self.client.agents.passages.search(self.agent_id, query=question, top_k=self.config.top_k)
        items = [(str(r.timestamp)[:10], r.content) for r in res.results]
        return Retrieved(render_items(items), [t for _, t in items])

    def close(self) -> None:
        if self.agent_id and not self.config.options.get("keep"):
            try:
                self.client.agents.delete(self.agent_id)
            except Exception:
                pass

    def describe(self) -> str:
        return f"letta archival memory via REST ({self.base_url}, top {self.config.top_k})"
