"""Builds the frozen E2 question set from RAW YAML only (no graph, no ownergraph imports):
python scripts/make_e2_questions.py  ->  data/e2/questions.json   (commit the file, then build the agents against it)."""
import json, random, re
from collections import Counter
from pathlib import Path
import yaml

RAW = Path("data/raw")
rnd = random.Random(20261017)


def load(text):
    try:
        return yaml.safe_load(text) or {}
    except Exception:
        return {}


keps = {}
for path, text in json.loads((RAW / "keps.json").read_text()).items():
    y = load(text)
    if isinstance(y, dict) and str(y.get("kep-number", "")).isdigit():
        keps[int(y["kep-number"])] = y
sigs = {s["dir"]: s for s in load((RAW / "sigs.yaml").read_text()).get("sigs", [])}
chairs = {d: sorted(c["github"] for c in (s.get("leadership", {}).get("chairs") or []) if c.get("github")) for d, s in sigs.items()}
gate_count = Counter(g["name"] for y in keps.values() for g in (y.get("feature-gates") or []) if isinstance(g, dict))
files = json.loads((RAW / "owners_at_head.json").read_text())
aliases = {k: [str(m).lstrip("@") for m in v] for k, v in (load(files["OWNERS_ALIASES"]).get("aliases") or {}).items()}
owners = {}
for p, t in files.items():
    if p == "OWNERS" or p.endswith("/OWNERS"):
        y = load(t)
        d = p[:-len("/OWNERS")] if p != "OWNERS" else ""
        opts = y.get("options") or {}
        owners[d] = (set(str(a).lstrip("@") for a in (y.get("approvers") or [])),
                     bool(y.get("no_parent_owners") or (isinstance(opts, dict) and opts.get("no_parent_owners"))))


def expand(names):
    out, seen, st = set(), set(), list(names)
    while st:
        n = st.pop()
        if n in aliases:
            if n not in seen:
                seen.add(n); st.extend(aliases[n])
        else:
            out.add(n)
    return out


def eligible(dirpath):
    parts = dirpath.split("/") if dirpath else []
    out = set()
    for i in range(len(parts), -1, -1):
        d = "/".join(parts[:i])
        if d in owners:
            out |= expand(owners[d][0])
            if owners[d][1]:
                break
    return out


Q = []
gated = sorted(n for n, y in keps.items() if any(isinstance(g, dict) and gate_count[g["name"]] == 1 for g in (y.get("feature-gates") or [])))
def gate_of(n):
    return next(g["name"] for g in keps[n]["feature-gates"] if isinstance(g, dict) and gate_count[g["name"]] == 1)

# multi-hop 1: gate -> KEP -> approvers (15)
cand = [n for n in gated if keps[n].get("approvers")]
for n in rnd.sample(cand, 15):
    g = gate_of(n)
    Q.append(dict(id=f"m1-{n}", kind="multi", type="gate_approvers", mode="set",
                  text=f"Which people are listed as approvers of the KEP that introduced the feature gate {g}?",
                  key=sorted(str(a).lstrip("@") for a in keps[n]["approvers"])))
used = {q["id"] for q in Q}
# multi-hop 2: gate -> KEP -> owning SIG -> chairs (15)
cand = [n for n in gated if keps[n].get("owning-sig") in chairs and chairs[keps[n]["owning-sig"]] and f"m1-{n}" not in used]
for n in rnd.sample(cand, 15):
    g = gate_of(n)
    Q.append(dict(id=f"m2-{n}", kind="multi", type="gate_sig_chairs", mode="set",
                  text=f"Who chairs the SIG that owns the KEP introducing the feature gate {g}?",
                  key=chairs[keps[n]["owning-sig"]]))
# multi-hop 3: file -> OWNERS inheritance + aliases -> eligible approvers; answer one or more eligible people (10)
dirs = [d for d in owners if d.count("/") >= 2 and owners[d][0] and any(a in aliases for a in owners[d][0])]
for d in rnd.sample(sorted(dirs), 10):
    f = d + "/example_test.go"
    Q.append(dict(id=f"m3-{d.replace('/', '_')}", kind="multi", type="path_eligible", mode="member",
                  text=f"Name up to three people who are allowed to approve a change to the file {f} according to the OWNERS files (including inherited OWNERS and aliases).",
                  key=sorted(eligible(d))))
# single-hop: owning SIG of KEP-N (10), status of KEP-N (10)
nums = sorted(n for n, y in keps.items() if y.get("owning-sig") and y.get("status"))
pick = rnd.sample(nums, 20)
for n in pick[:10]:
    Q.append(dict(id=f"s1-{n}", kind="single", type="kep_sig", mode="set", text=f"Which SIG owns KEP-{n}?", key=[keps[n]["owning-sig"]]))
for n in pick[10:]:
    Q.append(dict(id=f"s2-{n}", kind="single", type="kep_status", mode="set", text=f"What is the status of KEP-{n}?", key=[str(keps[n]["status"])]))
Path("data/e2").mkdir(parents=True, exist_ok=True)
Path("data/e2/questions.json").write_text(json.dumps(Q, indent=1))
print(Counter((q["kind"], q["type"]) for q in Q), len(Q))
