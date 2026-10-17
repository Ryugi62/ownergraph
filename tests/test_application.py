import pytest
from ownergraph.application.ask import AskService, Abstention
from ownergraph.application.route import route_issue
from ownergraph.application.sync import SyncService
from ownergraph.application.eval_e1 import LeakageError, pr_features, run_e1
from ownergraph.domain.model import PullRequest, Comment
from ownergraph.domain.orphans import KepRecord
from tests.fakes import FakeClock, FakeLlm, FakeRepo, d


def svc(repo=None, llm=None, log=None):
    log = log if log is not None else []
    return AskService(repo or FakeRepo(log), llm or FakeLlm(log=log), FakeClock(d(2026, 10, 1))), log


def test_abstains_without_path():  # AC-7
    repo = FakeRepo(); repo.eligible_rows = []
    llm = FakeLlm()
    s, _ = svc(repo, llm)
    ans = s.ask("who approves pkg/kubelet/kubelet.go ?")
    assert isinstance(ans, Abstention) and ans.cypher and "no evidence" in ans.text.lower()
    assert llm.calls == []  # no answer sentence generated


def test_answer_carries_cypher_and_urls():  # AC-11
    s, _ = svc()
    ans = s.ask("who approves pkg/kubelet/kubelet.go ?")
    assert not isinstance(ans, Abstention)
    assert len(ans.evidence.cypher) >= 1 and any(u.startswith("https://github.com/") for u in ans.evidence.urls)


def test_ask_returns_deterministic_path_before_llm():  # AC-20
    s, log = svc()
    ans = s.ask("who approves pkg/kubelet/kubelet.go ?")
    assert ans.evidence.rows  # evidence exists even when the LLM summary is skipped
    assert log.index("repo:eligible") < log.index("llm")
    s2, _ = svc(llm=FakeLlm())
    s2.llm.complete = lambda p: (_ for _ in ()).throw(RuntimeError("llm down"))
    ans2 = s2.ask("who approves pkg/kubelet/kubelet.go ?")
    assert ans2.evidence.rows and ans2.summary is None  # LLM failure never loses the path


def test_ranked_answer_prefers_recent_decider():
    s, _ = svc()
    ans = s.ask("who approves pkg/kubelet/kubelet.go ?")
    assert ans.ranking[0].login == "bob"  # eligible {alice,bob}, only bob has history


def test_route_issue_returns_sig_approvers_kep():  # AC-12
    repo = FakeRepo()
    llm = FakeLlm(replies=['["kubelet"]'])
    r = route_issue("kubelet crashes when sidecar restarts", repo, llm)
    assert r.sig == "sig-node" and len(r.approvers) == 3 and r.related_keps and r.draft_only is True


def test_route_issue_abstains_when_no_candidate():
    repo = FakeRepo(); repo.route_rows = []
    assert isinstance(route_issue("???", repo, FakeLlm(replies=["[]"])), Abstention)


def kep(n, status="provisional", at=d(2026, 10, 2)):
    return KepRecord(n, f"k{n}", "sig-a", status, approvers=frozenset({"a"}), updated_at=at)


class FakeFetcher:
    def __init__(self, keps, prs=()): self.k, self.p = keps, list(prs)
    def keps_since(self, since): return [k for k in self.k if since is None or k.updated_at > since]
    def prs_since(self, since): return [p for p in self.p if since is None or p.merged_at > since]


def test_incremental_sync_upserts_only_newer():  # AC-13
    repo = FakeRepo(); repo.keps[1] = {"status": "provisional"}
    repo.snapshot = d(2026, 10, 1)
    f = FakeFetcher([kep(1, "implementable", d(2026, 10, 2)), kep(2, "provisional", d(2026, 9, 1))])
    res = SyncService(f, repo, FakeClock(d(2026, 10, 5))).sync()
    assert res.upserted_keps == 1 and 2 not in repo.keps
    assert repo.snapshot == d(2026, 10, 5)
    assert res.changed_kep_statuses == [(1, "provisional", "implementable")]


def pr(n, at, author="u", approvers=("a",), files=("pkg/a/x.go",), **kw):
    return PullRequest(number=n, title=f"t{n}", body="", author=author, merged_at=at,
                       files=tuple(files), labels=(), approvers=frozenset(approvers), **kw)


def test_eval_e1_rejects_leakage():  # AC-14
    cutoff = d(2026, 8, 1)
    with pytest.raises(LeakageError):
        run_e1(train=[pr(1, d(2026, 8, 2))], test=[pr(2, d(2026, 8, 3))], methods={}, cutoff=cutoff)
    with pytest.raises(LeakageError):  # boundary: equal to cutoff is test side
        run_e1(train=[pr(1, cutoff)], test=[pr(2, d(2026, 8, 3))], methods={}, cutoff=cutoff)


def test_e1_features_exclude_comments():  # AC-19
    p = pr(1, d(2026, 8, 3), comments=(Comment("u", "/assign @bob", d(2026, 8, 3)),))
    f = pr_features(p)
    assert set(f) == {"title", "body", "files", "author"}
    assert "/assign" not in str(f)


def test_run_e1_scores_methods_and_excludes_self_approved_only():
    cutoff = d(2026, 8, 1)
    test = [pr(10, d(2026, 8, 3), approvers=("a",)), pr(11, d(2026, 8, 4), author="a", approvers=("a",))]
    out = run_e1(train=[], test=test, methods={"m": lambda f: ["a", "b"]}, cutoff=cutoff)
    assert out["n_eval"] == 1 and out["methods"]["m"]["all"]["hit@1"] == 1.0  # PR 11 has no non-author approver


def test_run_e1_reports_segments():
    cutoff = d(2026, 8, 1)
    test = [pr(10, d(2026, 8, 3), approvers=("a",)), pr(12, d(2026, 8, 4), approvers=("b",))]
    seg = lambda p: "hard" if p.number == 12 else "easy"
    out = run_e1(train=[], test=test, methods={"m": lambda f: ["a"]}, cutoff=cutoff, segment_of=seg)
    assert out["methods"]["m"]["hard"]["hit@3"] == 0.0 and out["methods"]["m"]["easy"]["hit@3"] == 1.0


def test_run_e1_exposes_paired_per_pr_hits_for_significance():
    cutoff = d(2026, 8, 1)
    test = [pr(10, d(2026, 8, 3), approvers=("a",)), pr(12, d(2026, 8, 4), approvers=("b",))]
    out = run_e1(train=[], test=test, methods={"m": lambda f: ["a"]}, cutoff=cutoff)
    assert out["per_pr_hit3"]["m"] == [1, 0] and len(out["per_pr_segments"]) == 2


def test_paired_bootstrap_ci_brackets_point_estimate():
    from ownergraph.application.stats import paired_bootstrap_diff
    a, b = [1, 1, 1, 0] * 25, [1, 0, 0, 0] * 25
    r = paired_bootstrap_diff(a, b, n=500)
    assert r["n"] == 100 and r["diff"] == 0.5 and r["ci95"][0] <= 0.5 <= r["ci95"][1]
    assert paired_bootstrap_diff([], [])["n"] == 0
