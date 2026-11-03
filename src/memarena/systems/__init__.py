"""Registry of memory systems and baselines."""

from __future__ import annotations

from ..errors import MemarenaError
from .base import MemorySystem, Retrieved, SystemConfig

BASELINES = ["full-context", "bm25", "embeddings"]
MEMORY = ["mem0", "letta", "supermemory"]
ALL = BASELINES + MEMORY


def build(name: str, config: SystemConfig, budget=None) -> MemorySystem:
    name = name.strip().lower()
    if name == "full-context":
        from .baselines import FullContext

        return FullContext(config, budget)
    if name == "bm25":
        from .baselines import BM25

        return BM25(config, budget)
    if name == "embeddings":
        from .baselines import Embeddings

        return Embeddings(config, budget)
    if name == "mem0":
        from .mem0_adapter import Mem0

        return Mem0(config, budget)
    if name == "letta":
        from .letta_adapter import Letta

        return Letta(config, budget)
    if name == "supermemory":
        from .supermemory_adapter import Supermemory

        return Supermemory(config, budget)
    raise MemarenaError(f"Unknown system '{name}'. Choose from: {', '.join(ALL)}.")


__all__ = ["ALL", "BASELINES", "MEMORY", "MemorySystem", "Retrieved", "SystemConfig", "build"]
