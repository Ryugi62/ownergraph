"""Pick graph tier weights on a VALIDATION split (cutoff 2026-07-01, test = July) - never on the August test set."""
import itertools, json, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, ".")
from ownergraph.adapters.falkordb_repository import FalkorRepository
from ownergraph.adapters.parsers import prs_from_text
from ownergraph.infrastructure.datafiles import read_text
from ownergraph.application.eval_e1 import run_e1
from ownergraph.application.graph_predictor import GraphPredictor
from ownergraph.domain.baselines import OwnersHistory
from ownergraph.infrastructure.e1_run import CachedRepo
from ownergraph.infrastructure.loader import load_profile, read_owners

raw = Path("data/snapshot")
cut = datetime(2026, 7, 1, tzinfo=timezone.utc); until = datetime(2026, 8, 1, tzinfo=timezone.utc)
prs = prs_from_text(read_text(raw, "prs.jsonl"))
train = [p for p in prs if p.merged_at < cut]
test = [p for p in prs if cut <= p.merged_at < until]
repo = FalkorRepository.embedded("data/val.db", graph="val")
if repo.stats()["nodes"]:
    repo.g.delete(); repo = FalkorRepository.embedded("data/val.db", graph="val")
load_profile(repo, raw, "e1", cut, lambda *_: None)
rules, aliases = read_owners(raw, "owners_at_cutoff.json")
hist = OwnersHistory(rules, aliases, train, cut)
cached = CachedRepo(repo)
rows = []
base = run_e1(train, test, {"owners_history": hist.predict}, cut)["methods"]["owners_history"]["all"]
print("val n", len(test), "owners_history val hit@3", base["hit@3"])
for kep, slf, nby, anc, sig in itertools.product([0, 1, 2, 4], [3], [0, 1e-4], [0, 1e-5], [0, 1e-6]):
    tw = {"kep": kep, "self": slf, "scope": 1.0, "nearby": nby, "ancestor": anc, "sig": sig}
    r = run_e1(train, test, {"g": GraphPredictor(cached, cut, tier_weights=tw).predict}, cut)["methods"]["g"]["all"]
    rows.append((r["hit@3"], r["hit@1"], tw))
rows.sort(key=lambda x: (-x[0], -x[1]))
for r in rows[:6]: print(r)
json.dump({"val_baseline_owners_history_hit3": base["hit@3"], "top": [{"hit@3": a, "hit@1": b, "weights": c} for a, b, c in rows]},
          open("results/val_tuning.json", "w"), indent=1)
