# Contributing

Thanks for helping. memarena is small on purpose: one OpenAI-compatible client, a few adapters,
a static viewer. Please keep changes in that spirit.

## Setup

```bash
uv sync --all-extras --group dev
uv run pytest
uv run ruff check src tests
```

The viewer lives in `viewer/` (React + Vite + TypeScript, custom CSS, no Tailwind):

```bash
cd viewer
npm ci
npm run dev      # serves the viewer; put a results.json in viewer/public/data to try it
npm run build    # writes the bundle into src/memarena/viewer_dist (commit it)
```

## Adding a memory system

1. Create `src/memarena/systems/<name>_adapter.py` with a class that implements `MemorySystem`
   (`ingest(history)` and `retrieve(question) -> Retrieved`). Return dated items with `render_items`.
2. Register it in `src/memarena/systems/__init__.py`.
3. Put its SDK in an optional extra in `pyproject.toml`, pinned with `==`.
4. Set `remote` to the service name if conversations leave the machine, so the privacy warning fires.
5. Add a test with a mock client in `tests/test_adapters.py`. CI never calls paid APIs or live services.

## Rules

- Tests must not call real model providers. Use the `FakeLLM` in `tests/conftest.py`.
- Never commit real chat exports, API keys or `.env` files.
- Recorded demo numbers must come from a real `memarena run`. Do not edit them by hand.
