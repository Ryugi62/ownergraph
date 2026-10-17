from __future__ import annotations
from datetime import datetime, timezone
from ownergraph.application.ports import QueryResult


def d(y, m, dd, h=0):
    return datetime(y, m, dd, h, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self, now): self._now = now
    def now(self): return self._now


class FakeLlm:
    """Deterministic stand-in: returns scripted replies, records calls."""
    def __init__(self, replies=None, log=None):
        self.replies = list(replies or [])
        self.calls = []
        self.log = log if log is not None else []
    def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        self.log.append("llm")
        return self.replies.pop(0) if self.replies else "summary"


class FakeRepo:
    def __init__(self, log=None):
        self.log = log if log is not None else []
        self.eligible_rows = [{"login": "alice"}, {"login": "bob"}]
        self.decider_rows = [{"login": "bob", "n": 5, "last": d(2026, 9, 1).isoformat(), "path": "pkg/kubelet"}]
        self.trail_rows = [{"gate": "SidecarContainers", "kep": 753, "sig": "sig-node", "approver": "dchen1107"}]
        self.route_rows = [{"sig": "sig-node", "approvers": ["bob", "alice", "carol", "dave"], "keps": [753]}]
        self.stale_rows = [{"kep": 1000, "sig": "sig-x"}]
        self.keps, self.prs, self.snapshot = {}, {}, None
    def _r(self, name, rows):
        self.log.append(f"repo:{name}")
        return QueryResult(cypher=f"MATCH /* {name} */ RETURN 1", params={}, rows=rows,
                           urls=["https://github.com/kubernetes/kubernetes/pull/1"] if rows else [])
    def eligible_approvers(self, path): return self._r("eligible", self.eligible_rows)
    def deciders(self, path, cutoff=None): return self._r("deciders", self.decider_rows)
    def decision_trail(self, key): return self._r("trail", self.trail_rows)
    def route_candidates(self, entities): return self._r("route", self.route_rows)
    def stale_decisions(self, sig=None): return self._r("stale", self.stale_rows)
    def find_entity(self, name): return self._r("find", [{"kind": "Sig", "id": name}])
    def reviewer_centrality(self, limit=10): return self._r("central", [{"login": "bob", "score": 0.2}, {"login": "alice", "score": 0.1}])
    def kep_status(self, number): return self.keps.get(number, {}).get("status")
    def upsert_keps(self, keps):
        for k in keps: self.keps[k.number] = {"status": k.status}
        return len(keps)
    def upsert_prs(self, prs):
        for p in prs: self.prs[p.number] = p
        return len(prs)
    def get_snapshot(self): return self.snapshot
    def set_snapshot(self, at): self.snapshot = at


class DriftFakeRepo(FakeRepo):
    def owners_listing(self): return {"pkg": {"x", "y", "z", "w"}, "lib": {"x"}}
    def active_approvers(self, since): return {"x"}
