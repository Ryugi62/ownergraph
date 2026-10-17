"""MCP server (stdio) exposing the seven graph tools. Every tool returns {cypher, rows, urls} or an abstention."""
from __future__ import annotations
import json
from mcp.server.fastmcp import FastMCP

from ..application.route import route_issue as _route
from ..application.serialize import answer_to_dict

TOOL_NAMES = ("find_entity", "approvers_for_path", "deciders_for_path", "explain_feature_gate", "route_issue", "stale_decisions", "reviewer_centrality")


def _qr(qr) -> dict:
    return {"abstained": not qr.rows, "evidence": {"cypher": [qr.cypher], "rows": qr.rows[:60], "urls": qr.urls}}


def build_server(service, repo, llm) -> FastMCP:
    mcp = FastMCP("ownergraph")

    @mcp.tool()
    def find_entity(name: str) -> dict:
        """Find a Sig, Person (GitHub handle), FeatureGate or Directory by name."""
        return _qr(repo.find_entity(name))

    @mcp.tool()
    def approvers_for_path(path: str) -> dict:
        """Who may approve a change to this repo path (OWNERS inheritance), ranked by who actually approved nearby recently."""
        return answer_to_dict(service.approvers_for_path(path))

    @mcp.tool()
    def deciders_for_path(path: str) -> dict:
        """Who actually approved PRs touching this path (history, with PR links)."""
        return _qr(repo.deciders(path))

    @mcp.tool()
    def explain_feature_gate(gate_or_kep: str) -> dict:
        """Decision trail: feature gate -> KEP -> owning SIG -> approvers."""
        return _qr(repo.decision_trail(gate_or_kep))

    @mcp.tool()
    def route_issue(text: str) -> dict:
        """Draft routing for a new issue: SIG, top-3 approvers, related KEPs. Never writes to GitHub."""
        r = _route(text, repo, llm)
        if getattr(r, "abstained", False):
            return {"abstained": True, "text": r.text}
        return {"abstained": False, "sig": r.sig, "approvers": r.approvers, "related_keps": r.related_keps,
                "draft_only": True, "evidence": {"cypher": r.evidence.cypher, "rows": r.evidence.rows}}

    @mcp.tool()
    def stale_decisions(sig: str = "") -> dict:
        """KEPs whose approvers hold no current approver or SIG leadership role (orphaned decisions)."""
        return _qr(repo.stale_decisions(sig or None))

    @mcp.tool()
    def reviewer_centrality(limit: int = 10) -> dict:
        """PageRank (FalkorDB algo.pageRank) over author -> approver reliance: the reviewers other contributors depend on most."""
        return _qr(repo.reviewer_centrality(max(1, min(limit, 25))))

    return mcp


def main():  # pragma: no cover
    from ..infrastructure.composition import build_services
    service, repo, llm = build_services()
    build_server(service, repo, llm).run()
