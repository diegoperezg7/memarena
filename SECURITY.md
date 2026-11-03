# Security policy

## Reporting a vulnerability

Please report security issues privately through
[GitHub security advisories](https://github.com/diegoperezg7/memarena/security/advisories/new).
Do not open a public issue. You should get an answer within a week.

## What memarena does with your data

- Your chat exports are read locally and written to local JSON files you control.
- With `--provider ollama` and the local systems (full-context, bm25, embeddings with Ollama, mem0 with Ollama),
  nothing leaves your machine.
- With a cloud provider, or with Supermemory or Letta Cloud, the conversations (or the parts each step needs)
  are sent to that service. memarena warns and asks before doing so; `--yes` skips the question.
- API keys are read only from environment variables and are never written to results files.
- memarena sends no telemetry and turns off mem0's telemetry (`MEM0_TELEMETRY=False`).
- mem0 2.2.1 routes its OpenAI-compatible calls to OpenRouter whenever `OPENROUTER_API_KEY` is set, even if
  another base URL is configured. memarena hides that variable from mem0 unless you chose OpenRouter.
- `memarena view` binds to 127.0.0.1 only. The only write endpoint saves the questions file you passed.
