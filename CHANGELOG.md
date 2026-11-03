# Changelog

## 0.1.0 - 2026-11-03

First release.

- Importers: ChatGPT export, Claude export (`conversations.json` or the `.zip`), generic JSONL.
- `memarena generate`: questions with gold answers and evidence pointers in LongMemEval's five categories
  (single-session, multi-session, temporal, knowledge update, abstention), written as `pending` for review.
- `memarena run`: systems mem0 (OSS), Letta (REST API) and Supermemory (API), always next to three baselines:
  full context, BM25 and embeddings. Same answer model and prompt for every system.
- Metrics: accuracy from an LLM judge (prompt published in `docs/judge-prompt.md`), retrieval latency p50/p95,
  ingestion time, prompt tokens and cost, overall and per category.
- Viewer (React) bundled in the wheel: `memarena view`, question review and editing, static export for Pages.
- `memarena demo`: a recorded real run on a 20-question LongMemEval subset (MIT).
- `--max-cost` budget checked before every paid call, privacy warning before sending data to a cloud provider.
