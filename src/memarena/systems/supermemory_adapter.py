"""Supermemory adapter (hosted API). Install with: uv tool install 'memarena[supermemory]'.

Needs SUPERMEMORY_API_KEY. Your conversations are sent to Supermemory's servers.
"""

from __future__ import annotations

import os
import time
import uuid

from ..errors import MissingKeyError, OptionalDependencyError
from ..models import History, chunk_history
from .base import MemorySystem, Retrieved, render_items


class Supermemory(MemorySystem):
    name = "supermemory"
    kind = "memory"
    remote = "supermemory"

    def __init__(self, config, budget=None, client=None) -> None:
        super().__init__(config, budget)
        if client is None:
            key = os.environ.get("SUPERMEMORY_API_KEY", "").strip()
            if not key:
                raise MissingKeyError(
                    "Missing API key: set SUPERMEMORY_API_KEY to benchmark Supermemory, "
                    "or drop it from --systems."
                )
            try:
                from supermemory import Supermemory as Client
            except ImportError as e:
                raise OptionalDependencyError(
                    "supermemory is not installed. Install the extra: uv tool install 'memarena[supermemory]'."
                ) from e
            client = Client(api_key=key)
        self.client = client
        self.namespace = config.options.get("supermemory_namespace") or f"memarena-{uuid.uuid4().hex[:10]}"
        self.wait_s = float(config.options.get("supermemory_wait", 30))

    def ingest(self, history: History) -> None:
        for c in chunk_history(history):
            self.client.add(
                namespace=self.namespace,
                content=c.text,
                date=c.date or None,
                metadata={"session_id": c.session_id, "date": c.date},
            )
        # Documents are processed asynchronously on the server side.
        if self.wait_s > 0:
            time.sleep(self.wait_s)

    def retrieve(self, question, question_date=None) -> Retrieved:
        res = self.client.search(namespace=self.namespace, query=question, limit=self.config.top_k)
        items = []
        for r in res.results:
            text = r.memory or r.chunk or ""
            items.append(((r.metadata or {}).get("date", ""), text))
        return Retrieved(render_items(items), [t for _, t in items])

    def describe(self) -> str:
        return f"supermemory API (namespace {self.namespace}, top {self.config.top_k})"
