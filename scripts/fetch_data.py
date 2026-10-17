"""Downloads the public inputs (needs `gh auth login` for the GraphQL token). ~150 GraphQL points, no private data."""
import sys, json
sys.path.insert(0, ".")
from datetime import date
from pathlib import Path
from ownergraph.adapters import github_fetcher as g
D = Path("data/raw"); D.mkdir(parents=True, exist_ok=True)
CUT = "2026-08-01T00:00:00Z"
sha = g.commit_before("kubernetes/kubernetes", CUT)
(D / "cutoff_sha.txt").write_text(sha); print("cutoff sha", sha, flush=True)
paths = g.owners_paths("kubernetes/kubernetes", sha)
files = g.fetch_files("kubernetes/kubernetes", sha, paths + ["OWNERS_ALIASES"])
(D / "owners_at_cutoff.json").write_text(json.dumps(files)); print("owners files", len(files), flush=True)
kp = g.kep_paths()
keps = g.fetch_files("kubernetes/enhancements", "master", kp)
(D / "keps.json").write_text(json.dumps(keps)); print("keps", len(keps), flush=True)
sigs = g.raw("kubernetes/community", "master", "sigs.yaml")
(D / "sigs.yaml").write_text(sigs or ""); print("sigs bytes", len(sigs or ""), flush=True)
head = g.gh_rest("repos/kubernetes/kubernetes/commits?per_page=1")[0]["sha"]
paths2 = g.owners_paths("kubernetes/kubernetes", head)
files2 = g.fetch_files("kubernetes/kubernetes", head, paths2 + ["OWNERS_ALIASES"])
(D / "owners_at_head.json").write_text(json.dumps(files2)); print("owners head", len(files2), flush=True)
n = g.fetch_merged_prs("kubernetes/kubernetes", date(2026, 5, 1), date(2026, 10, 17), D / "prs.jsonl")
print("prs", n, flush=True)
