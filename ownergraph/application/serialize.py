from __future__ import annotations
from dataclasses import asdict
from .ask import Abstention, Answer


def answer_to_dict(a) -> dict:
    ev = a.evidence
    d = {"abstained": bool(getattr(a, "abstained", False)), "tool": getattr(a, "tool", ""), "text": a.text,
         "summary": getattr(a, "summary", None),
         "evidence": {"cypher": (ev.cypher if ev else getattr(a, "cypher", [])) or getattr(a, "cypher", []),
                      "rows": (ev.rows if ev else [])[:60], "urls": ev.urls if ev else [],
                      "params": ev.params if ev else []}}
    if isinstance(a, Abstention):
        d["evidence"]["cypher"] = a.cypher or d["evidence"]["cypher"]
    if isinstance(a, Answer):
        d["ranking"] = [{"login": r.login, "score": r.score, "approvals": r.approvals} for r in a.ranking[:10]]
    return d
