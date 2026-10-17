"""UC-7 RunEvalE1: time-split evaluation of 'who actually approved'. Pre-registered in SPEC section 1."""
from __future__ import annotations
from collections import defaultdict
from ..domain.metrics import hit_at_k, mrr


class LeakageError(Exception):
    pass


def pr_features(pr) -> dict:
    """AC-19: only fields available when the PR opened. No comments (/assign etc.), no labels added later."""
    return {"title": pr.title, "body": pr.body, "files": list(pr.files), "author": pr.author}


def truth_of(pr) -> frozenset:
    return frozenset(pr.approvers) - {pr.author}


def run_e1(train, test, methods: dict, cutoff, segment_of=None, ks=(1, 3)) -> dict:
    for p in train:
        if p.merged_at >= cutoff:
            raise LeakageError(f"training PR #{p.number} merged {p.merged_at} >= cutoff {cutoff}")
    eval_set = [p for p in test if truth_of(p)]
    acc = {m: defaultdict(lambda: defaultdict(list)) for m in methods}
    sizes = defaultdict(int)
    for p in eval_set:
        segs = ["all"] + ([segment_of(p)] if segment_of else [])
        for s in segs:
            sizes[s] += 1
        feats, truth = pr_features(p), truth_of(p)
        for name, fn in methods.items():
            pred = [x for x in fn(feats) if x != p.author]
            for s in segs:
                a = acc[name][s]
                for k in ks:
                    a[f"hit@{k}"].append(hit_at_k(pred, truth, k))
                a["mrr"].append(mrr(pred, truth))
    out = {"cutoff": cutoff.isoformat(), "n_eval": len(eval_set), "segment_sizes": dict(sizes), "methods": {}}
    for name in methods:
        out["methods"][name] = {s: {"n": len(v["mrr"]), **{k: round(sum(x) / len(x), 4) for k, x in v.items()}}
                                 for s, v in acc[name].items()}
    return out
