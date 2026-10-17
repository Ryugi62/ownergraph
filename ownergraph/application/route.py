"""UC-4 RouteIssue: SIG + approvers + related KEPs as a DRAFT (never writes to the real repo)."""
from __future__ import annotations
import json, re
from dataclasses import dataclass, field
from .ask import Abstention, Evidence


@dataclass
class RouteProposal:
    sig: str
    approvers: list
    related_keps: list
    evidence: Evidence
    draft_only: bool = True
    abstained: bool = False


STOP = {"with", "when", "that", "this", "from", "have", "does", "into", "after", "before", "returns", "error", "fails", "failed", "crashes",
        "issue", "route", "triage", "cluster", "kubernetes", "should", "would", "while", "there", "which", "about", "using", "running"}


def components_without_llm(text: str, repo) -> list:
    """Deterministic fallback: a token counts only if it is the name of a real directory segment in the graph."""
    seen, out = set(), []
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", text.lower()):
        tok = tok[5:] if tok.startswith("kube-") and len(tok) > 8 else tok
        if tok in STOP or tok in seen:
            continue
        seen.add(tok)
        for row in repo.find_entity(tok).rows:
            if row.get("kind") == "Directory" and tok in str(row.get("id", "")).split("/"):
                out.append(tok)
                break
    return out[:8]


def route_issue(text: str, repo, llm):
    try:
        entities = json.loads(llm.complete(
            "List the Kubernetes components/subsystems named or implied by this issue as a JSON array of strings.\n" + text))
        entities = [str(e) for e in entities][:8]
    except Exception:
        entities = []
    if not entities:
        entities = components_without_llm(text, repo)
    if not entities:
        return Abstention("No evidence path: no component could be extracted from the issue.", [], tool="route_issue")
    qr = repo.route_candidates(entities)
    if not qr.rows:
        return Abstention("No evidence path in the graph for the extracted components.", [qr.cypher], tool="route_issue",
                          evidence=Evidence([qr.cypher], [], []))
    top = qr.rows[0]
    return RouteProposal(top["sig"], list(top.get("approvers", []))[:3], list(top.get("keps", [])),
                         Evidence([qr.cypher], qr.rows, qr.urls, [qr.params]))
