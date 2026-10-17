"""Paired bootstrap for the E1 difference between two methods (same PRs)."""
from __future__ import annotations
import random


def paired_bootstrap_diff(a: list, b: list, n: int = 5000, seed: int = 11, idx=None) -> dict:
    ids = list(range(len(a))) if idx is None else list(idx)
    if not ids:
        return {"n": 0, "diff": 0.0, "ci95": [0.0, 0.0]}
    rng = random.Random(seed)
    diffs = []
    for _ in range(n):
        s = [ids[rng.randrange(len(ids))] for _ in ids]
        diffs.append(sum(a[i] - b[i] for i in s) / len(s))
    diffs.sort()
    point = sum(a[i] - b[i] for i in ids) / len(ids)
    return {"n": len(ids), "diff": round(point, 4), "ci95": [round(diffs[int(0.025 * n)], 4), round(diffs[int(0.975 * n)], 4)]}
