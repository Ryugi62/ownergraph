"""Raw public files -> FalkorDB graph. `profile` e1 = state at the cutoff (leak-free), demo = everything to date."""
from __future__ import annotations
import json
from pathlib import Path

from ..adapters.parsers import parse_aliases, parse_kep, parse_owners, parse_sig_leaders, prs_from_text
from .datafiles import read_text

OWNERS_SUFFIX = "/OWNERS"


def read_owners(raw: Path, name: str):
    files = json.loads(read_text(raw, name))
    rules = {}
    for path, text in files.items():
        if path == "OWNERS" or path.endswith(OWNERS_SUFFIX):
            d = path[: -len("/OWNERS")] if path != "OWNERS" else ""
            rules[d] = parse_owners(d, text)
    aliases = parse_aliases(files.get("OWNERS_ALIASES", "aliases: {}"))
    return rules, aliases


def read_keps(raw: Path) -> list:
    out = []
    for path, text in json.loads(read_text(raw, "keps.json")).items():
        k = parse_kep(text, path)
        if k:
            out.append(k)
    return out


def load_profile(repo, raw: Path, profile: str, cutoff=None, log=print) -> dict:
    owners_file = "owners_at_cutoff.json" if profile == "e1" else "owners_at_head.json"
    rules, aliases = read_owners(raw, owners_file)
    prs = prs_from_text(read_text(raw, "prs.jsonl"))
    if profile == "e1":
        prs = [p for p in prs if p.merged_at < cutoff]
    keps = read_keps(raw)
    repo.load_owners(rules, aliases)
    log(f"owners {len(rules)} aliases {len(aliases)}")
    repo.upsert_keps(keps)
    log(f"keps {len(keps)}")
    sigs_text = read_text(raw, "sigs.yaml")
    if sigs_text:
        repo.load_sig_leaders(parse_sig_leaders(sigs_text))
    repo.upsert_prs(prs)
    repo.link_directory_tree()
    repo.link_ownership()
    if hasattr(repo, "link_reliance"):
        repo.link_reliance()
    log(f"prs {len(prs)}")
    return {"owners_files": len(rules), "aliases": len(aliases), "keps": len(keps), "prs": len(prs), **repo.stats()}
