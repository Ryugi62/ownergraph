"""UC-1 AskQuestion / UC-2 ApproversForPath / UC-3 ExplainDecision / UC-6 StaleDecisions.

Order is the point (AC-20): the deterministic graph result is computed first; the LLM only words it.
No path -> Abstention, no answer sentence (AC-7)."""
from __future__ import annotations
import json, re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..domain.ranking import Approval, rank_approvers
from .ports import QueryResult

PATH_RE = re.compile(r"(?<![\w/])([\w.\-]+(?:/[\w.\-*]+)+)")
KEP_RE = re.compile(r"\bKEP[- ]?(\d+)\b", re.I)
GATE_RE = re.compile(r"\b([A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+)\b")
CENTRAL_RE = re.compile(r"\b(load[- ]bearing|central\w*|pagerank|rel(?:y|ies|ied) on|most relied)\b", re.I)
STALE_RE = re.compile(r"\b(stale|orphan\w*|abandon\w*|no longer)\b", re.I)


@dataclass
class Evidence:
    cypher: list
    rows: list
    urls: list
    params: list = field(default_factory=list)


@dataclass
class Answer:
    tool: str
    text: str
    evidence: Evidence
    summary: Optional[str] = None
    ranking: list = field(default_factory=list)
    abstained: bool = False


@dataclass
class Abstention:
    text: str
    cypher: list
    abstained: bool = True
    tool: str = ""
    evidence: Optional[Evidence] = None


def _iso(v):
    return v if isinstance(v, datetime) else datetime.fromisoformat(str(v).replace("Z", "+00:00"))


class AskService:
    def __init__(self, repo, llm, clock):
        self.repo, self.llm, self.clock = repo, llm, clock

    # ---- routing (deterministic first, LLM only as fallback planner) ----
    def plan(self, question: str):
        m = PATH_RE.search(question)
        if m:
            return "approvers_for_path", m.group(1)
        m = KEP_RE.search(question)
        if m:
            return "explain_feature_gate", m.group(1)
        if STALE_RE.search(question):
            return "stale_decisions", None
        if CENTRAL_RE.search(question):
            return "reviewer_centrality", None
        m = GATE_RE.search(question)
        if m:
            return "explain_feature_gate", m.group(1)
        try:
            plan = json.loads(self.llm.complete(
                'Pick one tool for the question. JSON {"tool": one of approvers_for_path|explain_feature_gate|stale_decisions|find_entity, "arg": string}. Question: ' + question))
            return plan["tool"], plan.get("arg")
        except Exception:
            return None, None

    def ask(self, question: str):
        tool, arg = self.plan(question)
        if tool == "approvers_for_path":
            return self.approvers_for_path(arg, question)
        if tool == "explain_feature_gate":
            return self._simple("explain_feature_gate", self.repo.decision_trail(arg), question)
        if tool == "stale_decisions":
            return self._simple("stale_decisions", self.repo.stale_decisions(), question)
        if tool == "reviewer_centrality":
            qr = self.repo.reviewer_centrality(10)
            if not qr.rows:
                return Abstention("No evidence path in the graph; not answering.", [qr.cypher], tool=tool,
                                  evidence=Evidence([qr.cypher], [], []))
            text = "Most relied-on reviewers (FalkorDB PageRank over RELIES_ON, author -> approver): " + ", ".join(
                r["login"] for r in qr.rows[:5])
            return self._with_summary(Answer(tool, text, Evidence([qr.cypher], qr.rows, qr.urls, [qr.params])), question)
        if tool == "find_entity" and arg:
            return self._simple("find_entity", self.repo.find_entity(arg), question)
        return Abstention("No evidence path: the question did not map to a graph query.", [], tool=tool or "")

    def approvers_for_path(self, path: str, question: str = "", author: str = "", cutoff=None):
        elig = self.repo.eligible_approvers(path)
        if not elig.rows:
            return Abstention(f"No evidence path in the graph for `{path}`; not answering.", [elig.cypher],
                              tool="approvers_for_path", evidence=Evidence([elig.cypher], [], []))
        dec = self.repo.deciders(path, cutoff)
        approvals = []
        for r in dec.rows:
            at = _iso(r.get("at") or r.get("last"))
            for _ in range(int(r.get("n", 1))):
                approvals.append(Approval(r["login"], at, r.get("path", ""), float(r.get("w", 1.0))))
        ranked = rank_approvers({r["login"] for r in elig.rows}, approvals, author, self.clock.now())
        ev = Evidence([elig.cypher, dec.cypher], elig.rows + dec.rows, list(dict.fromkeys(elig.urls + dec.urls)),
                      [elig.params, dec.params])
        text = f"Eligible approvers for {path}, ranked by recent decisions: " + ", ".join(
            f"{r.login} ({r.approvals})" for r in ranked[:5])
        return self._with_summary(Answer("approvers_for_path", text, ev, ranking=ranked), question)

    def _simple(self, tool, qr: QueryResult, question):
        if not qr.rows:
            return Abstention("No evidence path in the graph; not answering.", [qr.cypher], tool=tool,
                              evidence=Evidence([qr.cypher], [], []))
        ev = Evidence([qr.cypher], qr.rows, qr.urls, [qr.params])
        return self._with_summary(Answer(tool, f"{len(qr.rows)} graph rows for {tool}.", ev), question)

    def _with_summary(self, ans: Answer, question: str) -> Answer:
        try:
            ans.summary = self.llm.complete(
                "Answer in one sentence using ONLY these graph rows.\nQuestion: " + question +
                "\nRows: " + json.dumps(ans.evidence.rows[:20], default=str))
        except Exception:
            ans.summary = None  # the deterministic path is already the answer
        return ans
