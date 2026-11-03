"""One OpenAI-compatible client for every provider, with cost tracking and a hard budget."""

from __future__ import annotations

import os
import random
import re
import time
from dataclasses import dataclass, field

import openai

from .errors import (
    BudgetExceededError,
    MemarenaError,
    MissingKeyError,
    ModelNotFoundError,
    ProviderUnreachableError,
)

LOCAL_PROVIDERS = {"ollama"}


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    key_env: str | None


def ollama_base_url() -> str:
    host = os.environ.get("OLLAMA_HOST", "").strip() or "http://localhost:11434"
    if not host.startswith("http"):
        host = "http://" + host
    return host.rstrip("/")


def get_provider(name: str) -> Provider:
    name = name.lower()
    if name == "ollama":
        return Provider("ollama", ollama_base_url() + "/v1", None)
    presets = {
        "openai": Provider("openai", "https://api.openai.com/v1", "OPENAI_API_KEY"),
        "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
        "mistral": Provider("mistral", "https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    }
    if name not in presets:
        raise MemarenaError(f"Unknown provider '{name}'. Use one of: ollama, openai, openrouter, mistral.")
    return presets[name]


def is_local(provider: str) -> bool:
    return provider.lower() in LOCAL_PROVIDERS


# USD per million tokens (input, output). List prices checked 2026-11; override with --price.
PRICES: dict[str, tuple[float, float]] = {
    "mistral-small-latest": (0.10, 0.30),
    "mistral-medium-latest": (0.40, 2.00),
    "mistral-large-latest": (2.00, 6.00),
    "codestral-latest": (0.30, 0.90),
    "ministral-8b-latest": (0.10, 0.10),
    "ministral-3b-latest": (0.04, 0.04),
    "open-mistral-nemo": (0.15, 0.15),
    "mistral-embed": (0.10, 0.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
}
# Unknown cloud models are priced conservatively so the budget errs on the safe side.
FALLBACK_PRICE = (5.0, 15.0)


def price_for(provider: str, model: str, override: tuple[float, float] | None = None) -> tuple[float, float]:
    if is_local(provider):
        return (0.0, 0.0)
    if override:
        return override
    key = model.split("/")[-1]
    return PRICES.get(model, PRICES.get(key, FALLBACK_PRICE))


@dataclass
class Budget:
    """Tracks spend across every client that shares it and refuses calls past the cap."""

    max_cost: float = 1.0
    spent: float = 0.0
    by_provider: dict[str, float] = field(default_factory=dict)

    def check(self, estimate: float = 0.0) -> None:
        if self.spent + estimate > self.max_cost:
            raise BudgetExceededError(
                f"Budget exceeded: spent ${self.spent:.4f}, next call would cost about ${estimate:.4f}, "
                f"limit is ${self.max_cost:g}. Raise it with --max-cost or use a local model "
                "(--provider ollama). Partial results were kept."
            )

    def add(self, provider: str, cost: float) -> None:
        self.spent += cost
        self.by_provider[provider] = self.by_provider.get(provider, 0.0) + cost


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: float = 0.0


_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def strip_thinking(text: str) -> str:
    text = _THINK_RE.sub("", text or "")
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip()


def approx_tokens(text: str) -> int:
    """Rough token estimate (about 4 characters per token). Used only for budgeting and truncation."""
    return max(1, len(text) // 4)


class LLM:
    """Chat and embeddings over the OpenAI-compatible API of any preset provider."""

    def __init__(
        self,
        provider: str,
        model: str,
        budget: Budget | None = None,
        price: tuple[float, float] | None = None,
        max_retries: int = 8,
        timeout: float = 600.0,
    ) -> None:
        self.provider = get_provider(provider)
        self.model = model
        self.budget = budget or Budget()
        self.price = price_for(self.provider.name, model, price)
        self.max_retries = max_retries
        api_key = "ollama"
        if self.provider.key_env:
            api_key = os.environ.get(self.provider.key_env, "").strip()
            if not api_key:
                raise MissingKeyError(
                    f"Missing API key: set the {self.provider.key_env} environment variable to use "
                    f"--provider {self.provider.name}, or use --provider ollama to stay local."
                )
        self.client = openai.OpenAI(
            base_url=self.provider.base_url, api_key=api_key, timeout=timeout, max_retries=0
        )

    @property
    def label(self) -> str:
        return f"{self.provider.name}/{self.model}"

    @property
    def local(self) -> bool:
        return is_local(self.provider.name)

    def _cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        pin, pout = self.price
        return (prompt_tokens * pin + completion_tokens * pout) / 1_000_000

    def _call(self, fn):
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            try:
                return fn()
            except openai.AuthenticationError as e:
                raise MissingKeyError(
                    f"{self.provider.name} rejected the API key in {self.provider.key_env}. Check it and retry."
                ) from e
            except openai.NotFoundError as e:
                hint = f" Run: ollama pull {self.model}" if self.local else ""
                raise ModelNotFoundError(
                    f"Model '{self.model}' was not found on {self.provider.name}.{hint}"
                ) from e
            except openai.APIConnectionError as e:
                if self.local:
                    raise ProviderUnreachableError(
                        f"Ollama is not reachable at {ollama_base_url()}. Start it with 'ollama serve' "
                        "or set OLLAMA_HOST."
                    ) from e
                if attempt >= self.max_retries:
                    raise ProviderUnreachableError(f"Could not reach {self.provider.base_url}: {e}") from e
            except (openai.RateLimitError, openai.InternalServerError, openai.APITimeoutError) as e:
                if attempt >= self.max_retries:
                    raise MemarenaError(
                        f"{self.provider.name} kept failing after {self.max_retries} retries "
                        f"({type(e).__name__}). Try again later or lower concurrency."
                    ) from e
            except openai.BadRequestError as e:
                msg = str(e)
                if "model" in msg.lower() and ("not found" in msg.lower() or "invalid" in msg.lower()):
                    raise ModelNotFoundError(f"Model '{self.model}' is not available: {msg}") from e
                raise MemarenaError(f"{self.provider.name} rejected the request: {msg}") from e
            time.sleep(min(60.0, delay) + random.uniform(0, 1))
            delay *= 2
        raise MemarenaError("unreachable")

    def chat(
        self,
        messages: list[dict],
        max_tokens: int = 512,
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> tuple[str, Usage]:
        est_in = sum(approx_tokens(m.get("content") or "") for m in messages)
        self.budget.check(self._cost(est_in, max_tokens))
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if self.local:
            # Local reasoning models (e.g. qwen3) spend output tokens on thinking before the answer;
            # Ollama returns that thinking in a separate field, so only the budget needs room.
            kwargs["max_tokens"] = max(max_tokens, 4096)
        resp = self._call(lambda: self.client.chat.completions.create(**kwargs))
        text = strip_thinking(resp.choices[0].message.content or "")
        u = resp.usage
        usage = Usage(
            prompt_tokens=getattr(u, "prompt_tokens", 0) or est_in,
            completion_tokens=getattr(u, "completion_tokens", 0) or approx_tokens(text),
        )
        usage.cost = self._cost(usage.prompt_tokens, usage.completion_tokens)
        self.budget.add(self.provider.name, usage.cost)
        return text, usage

    def embed(self, texts: list[str], batch: int = 64) -> tuple[list[list[float]], Usage]:
        out: list[list[float]] = []
        total = Usage()
        for i in range(0, len(texts), batch):
            chunk = texts[i : i + batch]
            est = sum(approx_tokens(t) for t in chunk)
            self.budget.check(self._cost(est, 0))
            resp = self._call(lambda c=chunk: self.client.embeddings.create(model=self.model, input=c))
            out.extend(d.embedding for d in resp.data)
            pt = getattr(resp.usage, "prompt_tokens", 0) or est if resp.usage else est
            cost = self._cost(pt, 0)
            total.prompt_tokens += pt
            total.cost += cost
            self.budget.add(self.provider.name, cost)
        return out, total
