"""memarena command line."""

from __future__ import annotations

import json
import sys
import tempfile
from importlib import resources
from pathlib import Path

import typer
from rich.console import Console

from . import __version__
from .errors import MemarenaError
from .llm import LLM, Budget, is_local
from .models import History, QuestionSet

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    help="Benchmark memory layers on your own conversations, not on someone else's leaderboard.",
)
console = Console()
err = Console(stderr=True)

SystemsOpt = typer.Option("full-context,bm25,embeddings,mem0", help="Comma-separated systems to compare.")


def _version(value: bool):
    if value:
        console.print(f"memarena {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(False, "--version", callback=_version, is_eager=True, help="Show version."),
):
    pass


def _price(price: str | None) -> tuple[float, float] | None:
    if not price:
        return None
    try:
        a, b = (float(x) for x in price.split(","))
        return a, b
    except ValueError as e:
        raise MemarenaError("--price must look like 0.10,0.30 (USD per million input,output tokens)") from e


def privacy_check(destinations: set[str], yes: bool) -> None:
    """Warn before conversations leave the machine. With Ollama only, nothing is sent anywhere."""
    if not destinations:
        console.print("[green]Privacy:[/green] everything runs locally; no conversation leaves this machine.")
        return
    names = ", ".join(sorted(destinations))
    console.print(
        f"[yellow]Privacy warning:[/yellow] your conversations (or parts of them) will be sent to: "
        f"[bold]{names}[/bold]. Use --provider ollama and local systems to keep everything on this machine."
    )
    if yes:
        return
    if not sys.stdin.isatty():
        raise MemarenaError(
            "Refusing to send conversations to a cloud provider without confirmation. Pass --yes."
        )
    if not typer.confirm("Continue?", default=False):
        raise typer.Exit(1)


@app.command("import")
def import_cmd(
    file: Path = typer.Argument(
        ..., help="conversations.json (ChatGPT or Claude export, or the .zip) or .jsonl"
    ),
    fmt: str = typer.Option("auto", "--format", help="auto, chatgpt, claude or jsonl"),
    out: Path = typer.Option(Path("history.json"), help="Where to write the memarena history."),
):
    """Convert a chat export into history.json."""
    from .importers import load_any

    h = load_any(file, fmt)
    if not h.sessions:
        raise MemarenaError(f"No conversations with user/assistant messages found in {file}.")
    h.save(out)
    msgs = sum(len(s.messages) for s in h.sessions)
    console.print(f"Imported {len(h.sessions)} sessions, {msgs} messages -> {out}")


@app.command()
def generate(
    history: Path = typer.Argument(..., help="history.json from 'memarena import'"),
    out: Path = typer.Option(Path("questions.json"), help="Editable questions file to write."),
    provider: str = typer.Option("ollama", help="ollama, openai, openrouter or mistral"),
    model: str = typer.Option("qwen3:4b", help="Model that writes the questions."),
    per_category: int = typer.Option(4, help="Questions per category (5 categories)."),
    seed: int = typer.Option(7),
    max_cost: float = typer.Option(1.0, help="Abort before spending more than this (USD)."),
    price: str = typer.Option(None, help="Override model price: 'in,out' USD per million tokens."),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Do not ask before sending data to a cloud provider."
    ),
):
    """Write questions with gold answers and evidence pointers, for you to review."""
    from .qa import generate as gen

    h = History.load(history)
    budget = Budget(max_cost)
    llm = LLM(provider, model, budget=budget, price=_price(price))
    privacy_check(set() if llm.local else {provider}, yes)
    with console.status("Generating questions...") as st:
        qs = gen(h, llm, per_category=per_category, seed=seed, progress=lambda m: st.update(m))
    qs.save(out)
    console.print(
        f"Wrote {len(qs.questions)} questions (status: pending) -> {out}. Spent ${budget.spent:.4f}.\n"
        f"Review them before running:  memarena view --questions {out} --history {history}"
    )


@app.command()
def run(
    history: Path = typer.Argument(..., help="history.json"),
    questions: Path = typer.Argument(..., help="questions.json (only 'approved' questions run)"),
    systems: str = SystemsOpt,
    out: Path = typer.Option(Path("results.json")),
    provider: str = typer.Option("ollama", help="Provider of the answer model (same for every system)."),
    model: str = typer.Option("qwen3:4b", help="Answer model."),
    judge_provider: str = typer.Option(None, help="Judge provider (default: same as --provider)."),
    judge_model: str = typer.Option(None, help="Judge model (default: same as --model)."),
    embed_provider: str = typer.Option("ollama"),
    embed_model: str = typer.Option("nomic-embed-text"),
    memory_provider: str = typer.Option("ollama", help="LLM provider used inside mem0 / Letta."),
    memory_model: str = typer.Option("qwen3:4b", help="LLM used inside mem0 / Letta."),
    top_k: int = typer.Option(10, help="Items each retriever returns."),
    max_context_tokens: int = typer.Option(100_000, help="Cap for the full-context baseline."),
    max_cost: float = typer.Option(1.0, help="Abort before spending more than this (USD)."),
    price: str = typer.Option(None, help="Override answer-model price: 'in,out' USD per million tokens."),
    include_pending: bool = typer.Option(False, help="Also run questions not yet approved."),
    workdir: Path = typer.Option(None, help="Where memory systems keep their stores (default: temp dir)."),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Do not ask before sending data to a cloud provider."
    ),
    num_ctx: int = typer.Option(16384, help="Ollama context window used by mem0's extraction calls."),
):
    """Ingest the history into every system, ask every question and judge the answers."""
    from .report import print_summary
    from .runner import Runner
    from .systems import ALL, SystemConfig

    names = [s.strip() for s in systems.split(",") if s.strip()]
    unknown = [n for n in names if n not in ALL]
    if unknown:
        raise MemarenaError(f"Unknown system(s): {', '.join(unknown)}. Choose from: {', '.join(ALL)}.")
    h = History.load(history)
    qs = QuestionSet.load(questions)
    budget = Budget(max_cost)
    answer_llm = LLM(provider, model, budget=budget, price=_price(price))
    judge_llm = LLM(judge_provider or provider, judge_model or model, budget=budget)
    dest = {p for p in (provider, judge_provider or provider) if not is_local(p)}
    if "embeddings" in names or "mem0" in names or "letta" in names:
        if not is_local(embed_provider):
            dest.add(embed_provider)
    if ("mem0" in names or "letta" in names) and not is_local(memory_provider):
        dest.add(memory_provider)
    if "supermemory" in names:
        dest.add("supermemory")
    privacy_check(dest, yes)
    cfg = SystemConfig(
        top_k=top_k,
        max_context_tokens=max_context_tokens,
        embed_provider=embed_provider,
        embed_model=embed_model,
        llm_provider=memory_provider,
        llm_model=memory_model,
        workdir=str(workdir) if workdir else "",
        options={"num_ctx": num_ctx},
    )
    meta_path = Path(questions).with_name("dataset.json")
    info = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    runner = Runner(
        h,
        qs,
        names,
        answer_llm,
        judge_llm,
        cfg,
        budget,
        out,
        include_pending,
        info,
        progress=lambda m: console.print(f"[dim]{m}[/dim]"),
    )
    try:
        result = runner.run()
    except MemarenaError:
        console.print(f"Partial results saved to {out}")
        raise
    print_summary(result, console)
    console.print(f"Results -> {out}.  Open them with:  memarena view {out}")


def _demo_dir() -> Path:
    return Path(str(resources.files("memarena") / "data" / "demo"))


@app.command()
def view(
    results: Path = typer.Argument(None, help="results.json to show"),
    questions: Path = typer.Option(None, help="questions.json to review and edit (saved in place)."),
    history: Path = typer.Option(None, help="history.json, to show the evidence behind each question."),
    port: int = typer.Option(8765),
    no_browser: bool = typer.Option(False, "--no-browser"),
):
    """Open the viewer on a results file and/or a questions file to review."""
    from .viewer import export_site, serve

    if not results and not questions:
        raise MemarenaError("Pass a results.json and/or --questions questions.json.")
    for p in (results, questions, history):
        if p and not Path(p).exists():
            raise MemarenaError(f"File not found: {p}")
    site = export_site(Path(tempfile.mkdtemp(prefix="memarena-view-")) / "site", results, questions, history)
    serve(site, port, not no_browser, Path(questions).resolve() if questions else None)


@app.command()
def export(
    results: Path = typer.Argument(..., help="results.json"),
    out: Path = typer.Option(Path("site"), help="Output folder (static, e.g. for GitHub Pages)."),
    questions: Path = typer.Option(None),
    history: Path = typer.Option(None),
):
    """Export the viewer plus your results as a static site."""
    from .viewer import export_site

    export_site(out, results, questions, history)
    console.print(f"Static viewer -> {out}/index.html")


@app.command()
def demo(
    view_: bool = typer.Option(True, "--view/--no-view", help="Open the viewer after printing the table."),
    port: int = typer.Option(8765),
    no_browser: bool = typer.Option(False, "--no-browser"),
):
    """Show a RECORDED real run on a LongMemEval subset. No keys, no Docker, no model calls."""
    from .report import print_summary
    from .viewer import export_site, serve

    d = _demo_dir()
    result = json.loads((d / "results.json").read_text(encoding="utf-8"))
    print_summary(result, console, recorded=True)
    console.print(
        "This is a recorded run produced with 'memarena run' (see meta above). "
        "Reproduce it with the commands in the README."
    )
    if view_:
        site = export_site(
            Path(tempfile.mkdtemp(prefix="memarena-demo-")) / "site",
            d / "results.json",
            d / "questions.json",
            d / "history.json",
        )
        serve(site, port, not no_browser)


@app.command()
def longmemeval(
    file: Path = typer.Argument(..., help="longmemeval_oracle.json (or _s) from Hugging Face"),
    out_dir: Path = typer.Option(Path("lme"), help="Folder for history.json and questions.json."),
    per_category: int = typer.Option(3),
    seed: int = typer.Option(7),
    max_chars: int = typer.Option(
        16000, help="Prefer questions whose sessions are under this many characters."
    ),
):
    """Convert a LongMemEval subset into memarena files (one merged history)."""
    from .longmemeval import convert, select

    items = json.loads(Path(file).read_text(encoding="utf-8"))
    cats = ["single-session", "multi-session", "temporal", "knowledge-update", "abstention"]
    chosen = select(items, {c: per_category for c in cats}, seed=seed, max_chars=max_chars)
    h, qs = convert(chosen)
    out_dir.mkdir(parents=True, exist_ok=True)
    h.save(out_dir / "history.json")
    qs.save(out_dir / "questions.json")
    (out_dir / "dataset.json").write_text(
        json.dumps(
            {
                "name": "LongMemEval subset (xiaowu0162/longmemeval-cleaned, " + Path(file).name + ")",
                "license": "MIT",
                "url": "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned",
                "seed": seed,
                "per_category": per_category,
                "max_chars": max_chars,
            },
            indent=1,
        )
    )
    console.print(f"{len(h.sessions)} sessions, {len(qs.questions)} questions -> {out_dir}")


def main() -> None:
    try:
        app()
    except MemarenaError as e:
        err.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        err.print("Interrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
