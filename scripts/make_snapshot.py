"""data/raw (GraphQL dumps) -> data/snapshot (compact, gzipped, committed). Comments are dropped; approvers are already extracted."""
import json, shutil, sys
from pathlib import Path
sys.path.insert(0, ".")
from ownergraph.adapters.parsers import pr_to_compact, read_prs
from ownergraph.infrastructure.datafiles import write_gz

raw, snap = Path("data/raw"), Path("data/snapshot")
snap.mkdir(parents=True, exist_ok=True)
prs = sorted(read_prs(raw / "prs.jsonl"), key=lambda p: p.number)
write_gz(snap, "prs.jsonl", "".join(json.dumps(pr_to_compact(p)) + "\n" for p in prs))
for name in ("keps.json", "owners_at_cutoff.json", "owners_at_head.json", "sigs.yaml"):
    write_gz(snap, name, (raw / name).read_text())
shutil.copy(raw / "cutoff_sha.txt", snap / "cutoff_sha.txt")
print(len(prs), "PRs;", sum(f.stat().st_size for f in snap.iterdir()) // 1024, "KiB")
