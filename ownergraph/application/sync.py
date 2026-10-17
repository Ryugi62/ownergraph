"""UC-5 SyncOrg: incremental upsert since the last Snapshot."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class SyncResult:
    upserted_keps: int
    upserted_prs: int
    changed_kep_statuses: list = field(default_factory=list)


class SyncService:
    def __init__(self, fetcher, repo, clock):
        self.fetcher, self.repo, self.clock = fetcher, repo, clock

    def sync(self) -> SyncResult:
        since = self.repo.get_snapshot()
        keps = self.fetcher.keps_since(since)
        changed = []
        for k in keps:
            old = self.repo.kep_status(k.number)
            if old is not None and old != k.status:
                changed.append((k.number, old, k.status))
        n_k = self.repo.upsert_keps(keps)
        n_p = self.repo.upsert_prs(self.fetcher.prs_since(since))
        self.repo.set_snapshot(self.clock.now())
        return SyncResult(n_k, n_p, changed)
