"""ApprovalNotifierParser: Prow bot comment -> actual approvers (AC-10)."""
from __future__ import annotations
import re
from .model import Comment

BOTS = {"k8s-ci-robot", "kubernetes-prow", "kubernetes-prow[bot]"}
_LINE = re.compile(r"approved by:(.*)", re.I)
_A = re.compile(r"<a [^>]*?(title=\"([^\"]*)\")?[^>]*>([^<]+)</a>", re.I)
_STAR = re.compile(r"\*([^*]+)\*(\(Author self-approved\))?")


def _names(line: str, author: str) -> set:
    out = set()
    for m in _A.finditer(line):
        name, selfapp = m.group(3).strip(), "self-approved" in (m.group(2) or "").lower()
        if not selfapp:
            out.add(name)
    rest = _A.sub(" ", line)
    for m in _STAR.finditer(rest):
        name = m.group(1).strip()
        if m.group(2) is None and name:
            out.add(name)
    return {n.lstrip("@") for n in out if n.lstrip("@") != author}


def parse_approval_notifier(comments, pr_author: str) -> frozenset:
    result = frozenset()
    for c in sorted((c for c in comments if c.author in BOTS), key=lambda c: c.created_at):
        body = c.body
        if "APPROVALNOTIFIER" not in body and "approved by:" not in body.lower():
            continue
        if "NOT APPROVED" in body:
            continue
        m = _LINE.search(body)
        if m:
            result = frozenset(_names(m.group(1), pr_author))
    return result
