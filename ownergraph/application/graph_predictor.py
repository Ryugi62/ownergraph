"""E1 graph method: eligible approvers and nearby approval history both come from FalkorDB queries; ranking is domain logic."""
from __future__ import annotations
from ..domain.ranking import Approval, rank_approvers
import re

from .ask import _iso

KEP_REF = re.compile(r"(?:KEP[- #]?|enhancements/(?:issues|pull)/|kubernetes/enhancements#)(\d{2,5})", re.I)


class GraphPredictor:
    def __init__(self, repo, now, max_dirs: int = 40, tier_weights: dict | None = None):
        self.repo, self.now, self.max_dirs, self.tw = repo, now, max_dirs, tier_weights

    def representative_files(self, feats) -> list:
        seen, out = set(), []
        for f in feats["files"]:
            d = f.rsplit("/", 1)[0] if "/" in f else ""
            if d not in seen:
                seen.add(d)
                out.append(f)
        return out[: self.max_dirs]

    def predict(self, feats, k: int = 10) -> list:
        elig, approvals = set(), []
        for f in self.representative_files(feats):
            elig |= {r["login"] for r in self.repo.eligible_approvers(f).rows}
            for r in self.repo.deciders(f, cutoff=self.now).rows:
                approvals.append(Approval(r["login"], _iso(r["at"]), r["path"], float(self.tw[r["tier"]] if self.tw and "tier" in r else r.get("w", 1.0))))
        if hasattr(self.repo, "kep_deciders"):
            text = feats["title"] + " " + feats["body"][:2000]
            for num in sorted({int(x) for x in KEP_REF.findall(text)}):
                for r in self.repo.kep_deciders(num, cutoff=self.now).rows:
                    approvals.append(Approval(r["login"], _iso(r["at"]), r["path"], float(self.tw["kep"] if self.tw and "kep" in self.tw else r.get("w", 1.0))))
        ranked = rank_approvers(elig, approvals, feats["author"], self.now)
        return [r.login for r in ranked[:k]]
