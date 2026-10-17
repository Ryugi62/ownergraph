"""ApproverRanker: eligible ∩ history, recency half-life 90 days (AC-4, AC-5)."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Approval:
    login: str
    at: datetime
    path: str = ""
    weight: float = 1.0  # graph proximity: closer directories count more


@dataclass(frozen=True)
class RankedApprover:
    login: str
    score: float
    approvals: int = 0


def rank_approvers(eligible, approvals, author: str, now: datetime, half_life_days: float = 90.0) -> list:
    score: dict = {}
    count: dict = {}
    for a in approvals:
        if a.login not in eligible:
            continue
        age = max((now - a.at).total_seconds() / 86400.0, 0.0)
        score[a.login] = score.get(a.login, 0.0) + a.weight * 0.5 ** (age / half_life_days)
        count[a.login] = count.get(a.login, 0) + 1
    cands = [c for c in eligible if c != author]
    ranked = [RankedApprover(c, round(score.get(c, 0.0), 6), count.get(c, 0)) for c in cands]
    ranked.sort(key=lambda r: (-r.score, r.login))
    return ranked
