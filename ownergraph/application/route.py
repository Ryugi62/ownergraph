"""UC-4 RouteIssue: SIG + approvers + related KEPs as a DRAFT (never writes to the real repo)."""
from __future__ import annotations
import json
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


def route_issue(text: str, repo, llm):
    try:
        entities = json.loads(llm.complete(
            "List the Kubernetes components/subsystems named or implied by this issue as a JSON array of strings.\n" + text))
        entities = [str(e) for e in entities][:8]
    except Exception:
        entities = []
    if not entities:
        return Abstention("No evidence path: no component could be extracted from the issue.", [], tool="route_issue")
    qr = repo.route_candidates(entities)
    if not qr.rows:
        return Abstention("No evidence path in the graph for the extracted components.", [qr.cypher], tool="route_issue",
                          evidence=Evidence([qr.cypher], [], []))
    top = qr.rows[0]
    return RouteProposal(top["sig"], list(top.get("approvers", []))[:3], list(top.get("keps", [])),
                         Evidence([qr.cypher], qr.rows, qr.urls, [qr.params]))
