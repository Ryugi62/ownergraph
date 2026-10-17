"""UC-8 RunEvalE2: held-out multi-hop questions. Answer keys come from raw YAML via a separate script (scripts/make_e2_questions.py)."""
from __future__ import annotations
import json, re
from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    id: str
    kind: str   # single | multi
    type: str
    text: str
    key: frozenset
    mode: str = "set"  # set = exact match, member = non-empty subset of key


def extract_list(text: str) -> list:
    m = re.search(r"\[[^\[\]]*\]", text or "", re.S)
    if not m:
        return []
    try:
        v = json.loads(m.group(0))
        return [str(x) for x in v]
    except (ValueError, TypeError):
        return []


def grade(q: Question, answer: str) -> bool:
    got = {x.strip().lower() for x in extract_list(answer) if str(x).strip()}
    key = {k.lower() for k in q.key}
    if q.mode == "member":
        return bool(got) and got <= key
    return got == key


def run_e2(questions, systems: dict) -> dict:
    n = {"single": 0, "multi": 0}
    for q in questions:
        n[q.kind] += 1
    out = {"n": n, "systems": {}, "by_type": {}, "failures": {}}
    for name, fn in systems.items():
        ok = {"single": 0, "multi": 0}
        by_type, fails = {}, []
        for q in questions:
            try:
                ans = fn(q)
            except Exception as e:  # a failing system answers nothing
                ans = f"ERROR {type(e).__name__}"
            good = grade(q, ans)
            ok[q.kind] += good
            t = by_type.setdefault(q.type, [0, 0])
            t[0] += good; t[1] += 1
            if not good:
                fails.append({"id": q.id, "answer": (ans or "")[:160]})
        out["systems"][name] = {k: round(ok[k] / n[k], 4) if n[k] else None for k in ok}
        out["by_type"][name] = {t: f"{a}/{b}" for t, (a, b) in by_type.items()}
        out["failures"][name] = fails
    if "graph" in systems and "rag" in systems and n["multi"]:
        out["ablation_multi_drop_pp"] = round(100 * (out["systems"]["graph"]["multi"] - out["systems"]["rag"]["multi"]), 1)
    return out
