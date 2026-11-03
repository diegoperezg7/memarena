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


def format_audit(audit) -> str:
    """English one-liner for a judge audit (structured dict, or a plain string from older files)."""
    if isinstance(audit, str):
        return audit
    fp = audit.get("false_positives", {})
    fn = audit.get("false_negatives", {})
    nfp, nfn = sum(fp.values()), sum(fn.values())
    text = f"{audit.get('checked')} decisions checked by hand: {nfp} false positives"
    if fp:
        text += " (" + ", ".join(f"{k} {v}" for k, v in fp.items()) + ")"
    text += f", {nfn} false negatives."
    corr = audit.get("corrected_accuracy")
    if corr:
        text += " Corrected: " + ", ".join(f"{k} {v * 100:.0f}%" for k, v in corr.items()) + "."
    return text


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
    if meta.get("judge_audit"):
        lines.append(f"judge audit: {format_audit(meta['judge_audit'])}")
    title = "RECORDED RUN (not live)" if recorded else "memarena results"
    if meta.get("status") == "aborted":
        title += f"  [aborted: {meta.get('abort_reason', '')[:80]}]"
    console.print(Panel("\n".join(lines), title=title, border_style="magenta"))
    cats = result.get("categories", list(SHORT))
    summary = result.get("summary", {})
    systems = result.get("systems", [])
    wide = console.width >= 150
    full = console.width >= 100  # room for p50 and ingestion next to the essentials

    t = Table(show_lines=False, header_style="bold")
    t.add_column("system", no_wrap=True)
    t.add_column("accuracy", justify="right")
    if wide:
        for c in cats:
            t.add_column(SHORT.get(c, c), justify="right")
    if full:
        t.add_column("p50 ms", justify="right")
    t.add_column("p95 ms", justify="right")
    if full:
        t.add_column("ingest s", justify="right")
    t.add_column("tok/q", justify="right")
    t.add_column("cost $", justify="right")
    for s in systems:
        row = summary.get(s["name"], {})
        name = s["name"] + (" *" if s.get("kind") == "baseline" else "")
        if s.get("error"):
            t.add_row(name, "[red]error[/red]", *["-"] * (len(t.columns) - 2))
            continue
        cells = [name, f"[bold]{_pct(row.get('accuracy'))}[/bold]"]
        if wide:
            bc = row.get("by_category", {})
            cells += [_pct(bc[c]["accuracy"]) if c in bc else "-" for c in cats]
        if full:
            cells.append(_ms(row.get("latency_p50_ms")))
        cells.append(_ms(row.get("latency_p95_ms")))
        if full:
            cells.append("-" if row.get("ingest_seconds") is None else f"{row['ingest_seconds']:.1f}")
        cells.append("-" if row.get("avg_prompt_tokens") is None else f"{row['avg_prompt_tokens']:.0f}")
        cells.append(f"{row.get('cost_usd', 0):.4f}")
        t.add_row(*cells)
    console.print(t)
    if not wide:
        c2 = Table(show_lines=False, header_style="bold", title="accuracy by category", title_justify="left")
        c2.add_column("system", no_wrap=True)
        for c in cats:
            c2.add_column(SHORT.get(c, c), justify="right")
        for s in systems:
            if s.get("error"):
                continue
            bc = summary.get(s["name"], {}).get("by_category", {})
            c2.add_row(s["name"], *[_pct(bc[c]["accuracy"]) if c in bc else "-" for c in cats])
        console.print(c2)
    console.print("[dim]* baseline · p50/p95: retrieval latency · tok/q: prompt tokens per question[/dim]")
    errs = [s for s in result.get("systems", []) if s.get("error")]
    for s in errs:
        console.print(f"[red]{s['name']}[/red]: {s['error']}")
    cost = result.get("cost", {})
    console.print(
        f"Total spent: ${cost.get('total_usd', 0):.4f} (judge included)  "
        "by provider: " + ", ".join(f"{k} ${v:.4f}" for k, v in (cost.get("by_provider") or {}).items())
    )
