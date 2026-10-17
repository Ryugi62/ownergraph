"""Wires E1: leak-free graph at the cutoff + four methods -> results JSON."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from ..adapters.falkordb_repository import FalkorRepository
from ..adapters.parsers import prs_from_text
from .datafiles import read_text
from ..application.eval_e1 import run_e1
from ..application.graph_predictor import GraphPredictor
from ..application.stats import paired_bootstrap_diff
from ..domain.baselines import OwnersHistory, ProwRandom, TfidfRetrieval
from ..domain.owners import eligible_approvers
from .loader import load_profile, read_owners

CUTOFF = datetime(2026, 8, 1, tzinfo=timezone.utc)


class CachedRepo:
    """Memoises read queries so weight sweeps do not re-query FalkorDB (same rows, same answers)."""
    def __init__(self, repo):
        self.repo, self._c = repo, {}

    def _memo(self, name, *args):
        k = (name,) + args
        if k not in self._c:
            self._c[k] = getattr(self.repo, name)(*args)
        return self._c[k]

    def eligible_approvers(self, path): return self._memo("eligible_approvers", path)
    def deciders(self, path, cutoff=None): return self._memo("deciders", path, cutoff)
    def kep_deciders(self, number, cutoff=None): return self._memo("kep_deciders", number, cutoff)


def run(raw: Path, db: str, out: Path, limit: int | None = None, log=print, cutoff=CUTOFF, until=None, tier_weights=None,
        graph_name="e1:kubernetes@2026-08-01") -> dict:
    CUTOFF_ = cutoff
    prs = prs_from_text(read_text(raw, "prs.jsonl"))
    train = [p for p in prs if p.merged_at < cutoff]
    test = sorted((p for p in prs if p.merged_at >= cutoff and (until is None or p.merged_at < until)), key=lambda p: p.number)
    if limit:
        test = test[:limit]
    repo = FalkorRepository.embedded(db, graph=graph_name)
    if repo.stats()["nodes"]:
        repo.g.delete()
        repo = FalkorRepository.embedded(db, graph=graph_name)
    stats = load_profile(repo, raw, "e1", cutoff, log)
    rules, aliases = read_owners(raw, "owners_at_cutoff.json")
    cached = CachedRepo(repo)
    hist = OwnersHistory(rules, aliases, train, cutoff)
    methods = {
        "prow_owners_random": ProwRandom(rules, aliases).predict,
        "tfidf_retrieval": TfidfRetrieval(train, cutoff).predict,
        "owners_history": hist.predict,
        "graph_local_only": GraphPredictor(cached, cutoff, tier_weights={"kep": 0, "self": 3, "scope": 1, "nearby": 0, "ancestor": 0, "sig": 0}).predict,
        "graph": GraphPredictor(cached, cutoff, tier_weights=tier_weights).predict,
    }

    def segs(p):
        f = {"files": list(p.files), "title": p.title}
        out = []
        dirs = hist.dirs_of(f)
        if not hist.has_history(f):
            out.append("no_nearby_history")
        if len(dirs) >= 2:
            out.append("multi_owners")
        if p.kep_refs:
            out.append("kep_linked")
        elig = set()
        for fl in p.files:
            elig |= eligible_approvers(fl, rules, aliases)
        active = {a for d in dirs for a in hist.table.get(d, {})}
        if elig and not (elig & active):
            out.append("eligible_all_inactive")
        out.append("hard" if out else "easy")
        return out

    res = run_e1(train, test, methods, cutoff, segment_of=segs)
    ph, segl = res.pop("per_pr_hit3"), res.pop("per_pr_segments")
    res["paired_graph_minus_owners_history_hit3"] = {}
    for seg in ["all", "hard", "easy", "no_nearby_history", "multi_owners", "kep_linked", "eligible_all_inactive"]:
        idx = [i for i, sg in enumerate(segl) if seg in sg]
        res["paired_graph_minus_owners_history_hit3"][seg] = paired_bootstrap_diff(ph["graph"], ph["owners_history"], idx=idx)
    res["graph_stats"] = stats
    res["train_prs"] = len(train)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2))
    return res
