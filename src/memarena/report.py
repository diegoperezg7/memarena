"""Terminal summary of a results.json."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

SHORT = {
    "single-session": "single",
    "multi-session": "multi",
    "temporal": "temporal",
    "knowledge-update": "update",
    "abstention": "abstain",
}


def _pct(x):
    return "-" if x is None else f"{x * 100:.0f}%"


def _ms(x):
    if x is None:
        return "-"
    return f"{x:.1f}" if x < 10 else f"{x:.0f}"


def print_summary(result: dict, console: Console | None = None, recorded: bool = False) -> None:
    console = console or Console()
    meta = result.get("meta", {})
    h = meta.get("history", {})
    lines = [
        f"memarena {meta.get('version', '?')}  |  {meta.get('created_at', '')[:16].replace('T', ' ')} UTC",
        f"answer model: {meta.get('answer_model')}  |  judge: {meta.get('judge_model')}",
        f"embeddings: {meta.get('embed_model')}  |  memory LLM: {meta.get('memory_llm')}",
        f"history: {h.get('sessions')} sessions, {h.get('messages')} messages, ~{h.get('approx_tokens')} tokens"
        f"  |  questions: {len(result.get('questions', []))}",
        f"hardware: {meta.get('hardware')}",
    ]
    ds = meta.get("dataset") or {}
    if ds.get("name"):
        lines.append(f"data: {ds['name']} ({ds.get('license', '')})")
    title = "RECORDED RUN (not live)" if recorded else "memarena results"
    if meta.get("status") == "aborted":
        title += f"  [aborted: {meta.get('abort_reason', '')[:80]}]"
    console.print(Panel("\n".join(lines), title=title, border_style="magenta"))
    cats = result.get("categories", list(SHORT))
    t = Table(show_lines=False, header_style="bold")
    t.add_column("system")
    t.add_column("accuracy", justify="right")
    for c in cats:
        t.add_column(SHORT.get(c, c), justify="right")
    t.add_column("p50 ms", justify="right")
    t.add_column("p95 ms", justify="right")
    t.add_column("ingest s", justify="right")
    t.add_column("prompt tok", justify="right")
    t.add_column("cost $", justify="right")
    summary = result.get("summary", {})
    for s in result.get("systems", []):
        row = summary.get(s["name"], {})
        if s.get("error"):
            t.add_row(s["name"], "[red]error[/red]", *["-"] * (len(cats) + 5))
            continue
        bc = row.get("by_category", {})
        t.add_row(
            s["name"] + (" [dim](baseline)[/dim]" if s.get("kind") == "baseline" else ""),
            f"[bold]{_pct(row.get('accuracy'))}[/bold]",
            *[_pct(bc[c]["accuracy"]) if c in bc else "-" for c in cats],
            _ms(row.get("latency_p50_ms")),
            _ms(row.get("latency_p95_ms")),
            "-" if row.get("ingest_seconds") is None else f"{row['ingest_seconds']:.1f}",
            "-" if row.get("avg_prompt_tokens") is None else f"{row['avg_prompt_tokens']:.0f}",
            f"{row.get('cost_usd', 0):.4f}",
        )
    console.print(t)
    errs = [s for s in result.get("systems", []) if s.get("error")]
    for s in errs:
        console.print(f"[red]{s['name']}[/red]: {s['error']}")
    cost = result.get("cost", {})
    console.print(
        f"Total spent: ${cost.get('total_usd', 0):.4f} (judge included)  "
        f"by provider: {cost.get('by_provider', {})}"
    )
