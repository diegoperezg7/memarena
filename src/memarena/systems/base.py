"""Interface every memory system and baseline implements."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..llm import Usage
from ..models import History


@dataclass
class Retrieved:
    context: str
    items: list[str] = field(default_factory=list)
    truncated: bool = False


@dataclass
class SystemConfig:
    """Settings shared by systems that need an LLM or embeddings of their own."""

    top_k: int = 10
    max_context_tokens: int = 100_000
    embed_provider: str = "ollama"
    embed_model: str = "nomic-embed-text"
    llm_provider: str = "ollama"  # LLM used inside memory systems (mem0 extraction, Letta agent)
    llm_model: str = "qwen3:4b"
    workdir: str = ""
    options: dict = field(default_factory=dict)


class MemorySystem:
    """Ingest a history once, then return context for each question.

    A system only decides what context reaches the answer model. The answer model and prompt are the
    same for every system, so accuracy differences come from memory alone.
    """

    name: str = "base"
    kind: str = "memory"  # "baseline" or "memory"
    #: provider used by the system itself, for privacy warnings ("local" means nothing leaves the machine)
    remote: str | None = None

    def __init__(self, config: SystemConfig, budget=None) -> None:
        self.config = config
        self.budget = budget
        self.usage = Usage()  # tokens and cost the system spent on its own (ingestion, embeddings)
        self.progress = lambda msg: None  # set by the runner

    def describe(self) -> str:
        return self.name

    def ingest(self, history: History) -> None:
        raise NotImplementedError

    def retrieve(self, question: str, question_date: str | None = None) -> Retrieved:
        raise NotImplementedError

    def close(self) -> None:
        pass

    def _add_usage(self, u: Usage) -> None:
        self.usage.prompt_tokens += u.prompt_tokens
        self.usage.completion_tokens += u.completion_tokens
        self.usage.cost += u.cost


def render_items(items: list[tuple[str, str]]) -> str:
    """items: (date, text) pairs, rendered oldest first."""
    items = sorted(items, key=lambda x: x[0] or "")
    return "\n\n".join(f"[{d or 'undated'}] {t}" for d, t in items)
