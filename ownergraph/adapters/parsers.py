"""Raw public files -> domain objects. People are GitHub handles only (PiiFilter)."""
from __future__ import annotations
import json, re
from datetime import datetime
import yaml

from ..domain.model import Comment, PullRequest
from ..domain.notifier import parse_approval_notifier
from ..domain.orphans import KepRecord
from ..domain.owners import OwnersRule
from ..domain.pii import filter_person

KEP_REF = re.compile(r"(?:KEP[- #]?|enhancements/(?:issues|pull)/|kubernetes/enhancements#)(\d{2,5})", re.I)


class _NoDateLoader(yaml.SafeLoader):
    """Fallback for real-world files with impossible dates (e.g. month 13): keep timestamps as plain strings."""


_NoDateLoader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag != "tag:yaml.org,2002:timestamp"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()}


def _load(text: str):
    try:
        return yaml.safe_load(text)
    except ValueError:
        return yaml.load(text, Loader=_NoDateLoader)


def _names(v) -> frozenset:
    return frozenset(str(x).lstrip("@").strip() for x in (v or []) if x)


def parse_owners(dir_path: str, text: str) -> OwnersRule:
    try:
        y = _load(text) or {}
    except (yaml.YAMLError, ValueError):
        y = {}
    if not isinstance(y, dict):
        y = {}
    approvers, reviewers = set(_names(y.get("approvers"))), set(_names(y.get("reviewers")))
    for pat, f in (y.get("filters") or {}).items():  # only whole-directory filters are modelled
        if pat in (".*", ".") and isinstance(f, dict):
            approvers |= _names(f.get("approvers"))
            reviewers |= _names(f.get("reviewers"))
    opts = y.get("options") or {}
    npo = bool(y.get("no_parent_owners") or (isinstance(opts, dict) and opts.get("no_parent_owners")))
    labels = y.get("labels") or []
    return OwnersRule(dir_path, frozenset(approvers), frozenset(reviewers), npo,
                      frozenset(l for l in labels if isinstance(l, str)))


def parse_aliases(text: str) -> dict:
    y = _load(text) or {}
    return {k: sorted(_names(v)) for k, v in (y.get("aliases") or {}).items()}


def parse_kep(text: str, path: str = "") -> KepRecord | None:
    try:
        y = _load(text) or {}
    except (yaml.YAMLError, ValueError):
        return None
    if not isinstance(y, dict):
        return None
    n = y.get("kep-number")
    try:
        n = int(n)
    except (TypeError, ValueError):
        m = re.search(r"/(\d+)-", path)
        if not m:
            return None
        n = int(m.group(1))
    gates = tuple(g.get("name") for g in (y.get("feature-gates") or []) if isinstance(g, dict) and g.get("name"))
    return KepRecord(n, str(y.get("title") or ""), y.get("owning-sig"), y.get("status"),
                     approvers=_names(y.get("approvers")), authors=_names(y.get("authors")),
                     participating_sigs=tuple(y.get("participating-sigs") or ()), feature_gates=gates,
                     stage=y.get("stage"), milestone=y.get("milestone") if isinstance(y.get("milestone"), dict) else None,
                     url=f"https://github.com/kubernetes/enhancements/blob/master/{path}" if path else "")


def parse_sig_leaders(text: str) -> dict:
    y = _load(text) or {}
    out = {}
    for s in y.get("sigs", []):
        sid = s.get("dir")
        people = []
        for key, role in (("chairs", "CHAIRS"), ("tech_leads", "LEADS")):
            for rec in (s.get("leadership", {}) or {}).get(key, []) or []:
                p = filter_person(rec)
                if p:
                    people.append((p["login"], role))
        if sid:
            out[sid] = people
    return out


def parse_pr(node: dict) -> PullRequest:
    author = (node.get("author") or {}).get("login") or "ghost"
    comments = tuple(Comment((c.get("author") or {}).get("login", ""), c.get("body", ""),
                             datetime.fromisoformat(c["createdAt"].replace("Z", "+00:00")))
                     for c in node["comments"]["nodes"] if c)
    text = node["title"] + " " + (node.get("bodyText") or "")[:2000]
    return PullRequest(
        number=node["number"], title=node["title"], body=(node.get("bodyText") or "")[:2000], author=author,
        merged_at=datetime.fromisoformat(node["mergedAt"].replace("Z", "+00:00")),
        files=tuple(f["path"] for f in node["files"]["nodes"]),
        labels=tuple(l["name"] for l in node["labels"]["nodes"]),
        approvers=parse_approval_notifier(comments, author), comments=comments,
        kep_refs=tuple(sorted({int(x) for x in KEP_REF.findall(text)})), url=node.get("url", ""))


def read_prs(path) -> list:
    return [parse_pr(json.loads(l)) for l in open(path) if l.strip()]
