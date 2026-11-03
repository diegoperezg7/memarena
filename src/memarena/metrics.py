"""Small, dependency-free statistics helpers."""

from __future__ import annotations


def percentile(values: list[float], p: float) -> float | None:
    """Linear-interpolated percentile (same as numpy's default). p in [0, 100]."""
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def summarize(answers: list[dict], systems: list[dict], categories: list[str]) -> dict:
    out: dict = {}
    for s in systems:
        name = s["name"]
        rows = [a for a in answers if a["system"] == name and a.get("correct") is not None]
        lat = [a["retrieval_ms"] for a in rows if a.get("retrieval_ms") is not None]
        by_cat = {}
        for c in categories:
            cr = [a for a in rows if a["category"] == c]
            if cr:
                ok = sum(1 for a in cr if a["correct"])
                by_cat[c] = {"n": len(cr), "correct": ok, "accuracy": ok / len(cr)}
        n = len(rows)
        ok = sum(1 for a in rows if a["correct"])
        ctx = [a["prompt_tokens"] for a in rows if a.get("prompt_tokens")]
        out[name] = {
            "n": n,
            "correct": ok,
            "accuracy": (ok / n) if n else None,
            "by_category": by_cat,
            "latency_p50_ms": percentile(lat, 50),
            "latency_p95_ms": percentile(lat, 95),
            "ingest_seconds": s.get("ingest_seconds"),
            "avg_prompt_tokens": (sum(ctx) / len(ctx)) if ctx else None,
            "cost_usd": (s.get("ingest_cost") or 0.0)
            + sum((a.get("answer_cost") or 0.0) + (a.get("retrieval_cost") or 0.0) for a in rows),
            "judge_cost_usd": sum(a.get("judge_cost") or 0.0 for a in rows),
            "error": s.get("error"),
        }
    return out
