import httpx
import openai
import pytest

from memarena.errors import (
    BudgetExceededError,
    MemarenaError,
    MissingKeyError,
    ModelNotFoundError,
    ProviderUnreachableError,
)
from memarena.llm import LLM, Budget, get_provider, price_for, strip_thinking


def test_missing_key_names_the_variable(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    with pytest.raises(MissingKeyError, match="MISTRAL_API_KEY"):
        LLM("mistral", "mistral-small-latest")


def test_unknown_provider():
    with pytest.raises(MemarenaError, match="Unknown provider"):
        get_provider("groqq")


def test_ollama_host_override(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "10.0.0.5:11434")
    assert get_provider("ollama").base_url == "http://10.0.0.5:11434/v1"


def test_prices():
    assert price_for("ollama", "qwen3:4b") == (0.0, 0.0)
    assert price_for("mistral", "ministral-8b-latest") == (0.10, 0.10)
    assert price_for("openrouter", "openai/gpt-4o-mini") == (0.15, 0.60)
    assert price_for("openai", "unknown-model") == (5.0, 15.0)
    assert price_for("openai", "unknown-model", (1, 2)) == (1, 2)


def test_budget_blocks_before_the_call(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    llm = LLM("openai", "gpt-4o-mini", budget=Budget(max_cost=0.0000001))
    called = []
    monkeypatch.setattr(llm.client.chat.completions, "create", lambda **k: called.append(k))
    with pytest.raises(BudgetExceededError, match="--max-cost"):
        llm.chat([{"role": "user", "content": "hello " * 1000}])
    assert called == []


def _req():
    return httpx.Request("POST", "http://localhost:11434/v1/chat/completions")


def test_ollama_unreachable_is_actionable(monkeypatch):
    llm = LLM("ollama", "qwen3:4b")

    def boom(**k):
        raise openai.APIConnectionError(request=_req())

    monkeypatch.setattr(llm.client.chat.completions, "create", boom)
    with pytest.raises(ProviderUnreachableError, match="ollama serve"):
        llm.chat([{"role": "user", "content": "hi"}])


def test_model_not_found_suggests_pull(monkeypatch):
    llm = LLM("ollama", "nope:1b")

    def boom(**k):
        raise openai.NotFoundError("model not found", response=httpx.Response(404, request=_req()), body=None)

    monkeypatch.setattr(llm.client.chat.completions, "create", boom)
    with pytest.raises(ModelNotFoundError, match="ollama pull nope:1b"):
        llm.chat([{"role": "user", "content": "hi"}])


def test_rate_limit_retries_then_succeeds(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    monkeypatch.setattr("memarena.llm.time.sleep", lambda s: None)
    llm = LLM("mistral", "ministral-8b-latest", max_retries=3)
    attempts = []

    class Resp:
        class _C:
            class message:
                content = "<think>hmm</think>Denver"

        choices = [_C]

        class usage:
            prompt_tokens = 1000
            completion_tokens = 10

    def flaky(**k):
        attempts.append(1)
        if len(attempts) < 3:
            raise openai.RateLimitError("429", response=httpx.Response(429, request=_req()), body=None)
        return Resp

    monkeypatch.setattr(llm.client.chat.completions, "create", flaky)
    text, usage = llm.chat([{"role": "user", "content": "hi"}])
    assert text == "Denver" and len(attempts) == 3
    assert usage.cost == pytest.approx((1000 * 0.10 + 10 * 0.10) / 1e6)
    assert llm.budget.by_provider["mistral"] == pytest.approx(usage.cost)


def test_strip_thinking():
    assert strip_thinking("<think>a\nb</think>\n answer") == "answer"
    assert strip_thinking("leftover</think>ok") == "ok"
