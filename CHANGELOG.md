# Changelog

## 0.1.2 - 2026-11-03

- Include LongMemEval MIT notice with the bundled demo data
  (`src/memarena/data/demo/LICENSE-LongMemEval.txt`, copied unmodified from xiaowu0162/LongMemEval) and cite it
  in a "Third-party data" section of the README.

## 0.1.1 - 2026-11-03

- Terminal: `memarena demo` and `run` fit narrow terminals (80 columns, CI logs, pipes). Below 150 columns the
  per-category accuracy moves to a second table; below 100 columns p50 and ingestion time are dropped.
- Viewer: the judge audit is stored as structured data and shown in the viewer's language (EN/ES).
- Viewer: system cards share one layout (kind chip under the name), so they line up.
- Viewer: answers render the bold/italic/code markdown models emit instead of showing raw asterisks; latency and
  token counts sit on their own line in every answer card; the question field is labelled "Question"; Spanish
  cards say "correctas".
- Viewer: deep links `#questions`, `#method` and `#q=<question id>` open a tab or expand a question.

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
