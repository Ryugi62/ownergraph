"""Problem-size numbers for the README (aggregates only, no person-level output). Reproduce: OWNERGRAPH_DB=data/ownergraph.db python scripts/problem_size.py"""
import json, os, sys
from datetime import timedelta
sys.path.insert(0, ".")
from ownergraph.adapters.parsers import prs_from_text
from ownergraph.domain.health import summarize_drift
from ownergraph.infrastructure.composition import make_repo
from ownergraph.infrastructure.datafiles import read_text

repo = make_repo()
latest = max(p.merged_at for p in prs_from_text(read_text(__import__("pathlib").Path("data/snapshot"), "prs.jsonl")))
since = latest - timedelta(days=90)
s = summarize_drift(repo.owners_listing(), repo.active_approvers(since))
nonempty = [f for f in s.files if f.listed]
out = {"window": f"{since.date()}..{latest.date()}", "owners_files_with_approvers": len(nonempty),
       "unique_listed_approver_handles": s.unique_approvers, "listed_with_zero_approvals_in_window": s.inactive_approvers,
       "inactive_share": round(s.inactive_share, 3),
       "owners_files_with_health_le_0.25": sum(1 for f in nonempty if f.ratio <= 0.25),
       "orphaned_decisions_open_keps": len(repo.stale_decisions().rows)}
os.makedirs("results", exist_ok=True)
json.dump(out, open("results/problem_size.json", "w"), indent=1)
print(json.dumps(out, indent=1))
