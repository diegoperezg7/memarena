"""LLM-as-a-judge grading. The prompt lives in prompts.py and docs/judge-prompt.md."""

from __future__ import annotations

import json
import re

from .llm import LLM, Usage
from .prompts import JUDGE_SYSTEM, JUDGE_USER


def parse_json_object(text: str) -> dict | None:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def judge(llm: LLM, category: str, question: str, answer: str, response: str) -> tuple[bool, str, Usage]:
    prompt = JUDGE_USER.format(category=category, question=question, answer=answer, response=response)
    text, usage = llm.chat(
        [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": prompt}],
        max_tokens=150,
        json_mode=True,
    )
    obj = parse_json_object(text)
    if obj is None or "correct" not in obj:
        low = text.lower()
        return (
            ('"correct": true' in low or low.startswith("true")),
            f"unparsed judge output: {text[:120]}",
            usage,
        )
    val = obj["correct"]
    correct = val is True or (isinstance(val, str) and val.strip().lower() == "true")
    return correct, str(obj.get("reason", ""))[:300], usage
