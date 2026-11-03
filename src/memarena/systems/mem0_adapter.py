"""mem0 (open-source, local) adapter. Install with: uv tool install 'memarena[mem0]'."""

from __future__ import annotations

import contextlib
import functools
import logging
import os
import tempfile
from pathlib import Path

from ..errors import OptionalDependencyError, ProviderUnreachableError
from ..llm import LLM, approx_tokens, get_provider, is_local, ollama_base_url
from ..models import History, chunk_history
from .base import MemorySystem, Retrieved, render_items

USER_ID = "memarena"


class Mem0(MemorySystem):
    """mem0 OSS with an LLM extracting facts from every turn and a local Qdrant store."""

    name = "mem0"
    kind = "memory"
    max_reply_chars = 1500  # assistant replies are long; mem0 extracts facts about the user

    def __init__(self, config, budget=None) -> None:
        super().__init__(config, budget)
        os.environ["MEM0_TELEMETRY"] = "False"  # memarena never sends telemetry, nor lets deps do it
        logging.getLogger("mem0").setLevel(logging.ERROR)  # optional-extra notices (spaCy, fastembed)
        try:
            from mem0 import Memory
        except ImportError as e:
            raise OptionalDependencyError(
                "mem0 is not installed. Install the extra: uv tool install 'memarena[mem0]' "
                "or run with: uvx --from 'memarena[mem0]' memarena run ..."
            ) from e
        self.workdir = Path(config.workdir or tempfile.mkdtemp(prefix="memarena-mem0-"))
        self.workdir.mkdir(parents=True, exist_ok=True)
        remote = [p for p in (config.llm_provider, config.embed_provider) if not is_local(p)]
        self.remote = remote[0] if remote else None
        self.infer = bool(config.options.get("mem0_infer", True))
        self._llm_price = LLM(config.llm_provider, config.llm_model, budget=budget)  # validates key early
        dims = len(LLM(config.embed_provider, config.embed_model, budget=budget).embed(["probe"])[0][0])
        mem_cfg = {
            "llm": self._component(config.llm_provider, config.llm_model, llm=True),
            "embedder": self._component(config.embed_provider, config.embed_model, llm=False),
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": "memarena",
                    "path": str(self.workdir / "qdrant"),
                    "embedding_model_dims": dims,
                    "on_disk": True,
                },
            },
            "history_db_path": str(self.workdir / "history.db"),
        }
        # mem0's OpenAI client silently switches to OpenRouter whenever OPENROUTER_API_KEY is set,
        # ignoring openai_base_url. Hide the variable while mem0 builds its clients, unless the user
        # actually asked for OpenRouter, so conversations go only where the user said.
        self._hide_openrouter = "openrouter" not in (config.llm_provider, config.embed_provider)
        with self._env_guard():
            self.memory = Memory.from_config(mem_cfg)
        self._patch_llm()

    @contextlib.contextmanager
    def _env_guard(self):
        hidden = os.environ.pop("OPENROUTER_API_KEY", None) if self._hide_openrouter else None
        try:
            yield
        finally:
            if hidden is not None:
                os.environ["OPENROUTER_API_KEY"] = hidden

    @staticmethod
    def _component(provider: str, model: str, llm: bool) -> dict:
        if is_local(provider):
            cfg = {"model": model, "ollama_base_url": ollama_base_url()}
            if llm:
                cfg.update(temperature=0.0, max_tokens=2000)
            else:
                cfg["embedding_dims"] = None
                cfg.pop("embedding_dims")
            return {"provider": "ollama", "config": cfg}
        p = get_provider(provider)
        key = os.environ.get(p.key_env or "", "")
        if llm:
            return {
                "provider": "openai",
                # Mistral rejects top_p != 1 with greedy sampling; mem0's default is 0.1.
                "config": {
                    "model": model,
                    "openai_base_url": p.base_url,
                    "api_key": key,
                    "temperature": 0.0,
                    "top_p": 1.0,
                },
            }
        return {
            "provider": "openai",
            "config": {"model": model, "openai_base_url": p.base_url, "api_key": key},
        }

    def _patch_llm(self) -> None:
        """Count mem0's own LLM calls against the budget and give local models a large enough window."""
        llm = self.memory.llm
        if is_local(self.config.llm_provider) and hasattr(llm, "client"):
            orig_chat = llm.client.chat

            @functools.wraps(orig_chat)
            def chat(**params):
                # mem0's extraction prompt alone is ~6k tokens; Ollama's default window would cut it.
                opts = dict(params.get("options") or {})
                opts["num_ctx"] = int(self.config.options.get("num_ctx", 16384))
                opts["num_predict"] = max(int(opts.get("num_predict") or 0), 8192)
                params["options"] = opts
                return orig_chat(**params)

            llm.client.chat = chat
        orig = llm.generate_response
        meter = self._llm_price

        @functools.wraps(orig)
        def generate_response(messages, *a, **kw):
            est_in = sum(approx_tokens(str(m.get("content", ""))) for m in messages)
            if self.budget is not None:
                self.budget.check(meter._cost(est_in, 2000))
            with self._env_guard():
                out = orig(messages, *a, **kw)
            text = out if isinstance(out, str) else str(out)
            cost = meter._cost(est_in, approx_tokens(text))
            self.usage.prompt_tokens += est_in
            self.usage.completion_tokens += approx_tokens(text)
            self.usage.cost += cost
            if self.budget is not None:
                self.budget.add(meter.provider.name, cost)
            return out

        llm.generate_response = generate_response

    def ingest(self, history: History) -> None:
        chunks = chunk_history(history)
        try:
            for n, c in enumerate(chunks, 1):
                msgs = []
                for line_role, text in _split_turn(c.text):
                    if line_role == "assistant":
                        text = text[: self.max_reply_chars]
                    msgs.append({"role": line_role, "content": text})
                if not msgs:
                    continue
                msgs[0]["content"] = f"(Conversation date: {c.date or 'unknown'}) " + msgs[0]["content"]
                self.memory.add(
                    msgs,
                    user_id=USER_ID,
                    metadata={"session_id": c.session_id, "date": c.date},
                    infer=self.infer,
                )
                if n % 10 == 0 or n == len(chunks):
                    self.progress(f"[mem0] ingested {n}/{len(chunks)} turns")
        except Exception as e:  # mem0 wraps provider errors in its own types
            _reraise(e)

    def retrieve(self, question, question_date=None) -> Retrieved:
        try:
            res = self.memory.search(question, top_k=self.config.top_k, filters={"user_id": USER_ID})
        except Exception as e:
            _reraise(e)
        results = res.get("results", res) if isinstance(res, dict) else res
        items = []
        for r in results or []:
            meta = r.get("metadata") or {}
            items.append((meta.get("date", ""), r.get("memory", "")))
        return Retrieved(render_items(items), [t for _, t in items])

    def close(self) -> None:
        try:
            self.memory.vector_store.client.close()
        except Exception:
            pass

    def describe(self) -> str:
        return (
            f"mem0 2.2.1 (LLM {self.config.llm_provider}/{self.config.llm_model}, "
            f"embeddings {self.config.embed_provider}/{self.config.embed_model}, top {self.config.top_k})"
        )


def _split_turn(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for line in text.split("\n"):
        for role in ("user", "assistant"):
            if line.startswith(role + ": "):
                out.append((role, line[len(role) + 2 :]))
                break
        else:
            if out:
                out[-1] = (out[-1][0], out[-1][1] + "\n" + line)
    return out


def _reraise(e: Exception):
    msg = str(e)
    if "Connection refused" in msg or "ConnectError" in type(e).__name__ or "Failed to connect" in msg:
        raise ProviderUnreachableError(
            f"mem0 could not reach its model provider ({msg[:200]}). Is Ollama running? Try 'ollama serve'."
        ) from e
    raise e
