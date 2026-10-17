import pytest
from ownergraph.domain.owners import OwnersRule, eligible_approvers, expand_aliases
from ownergraph.domain.ranking import Approval, rank_approvers
from ownergraph.domain.metrics import hit_at_k, mrr
from ownergraph.domain.pii import filter_person
from ownergraph.domain.notifier import Comment, parse_approval_notifier
from ownergraph.domain.health import owners_health
from ownergraph.domain.orphans import KepRecord, orphaned_decisions
from tests.fakes import d

R = OwnersRule


def rules(*rs): return {r.path: r for r in rs}


def test_owners_inheritance_unions_ancestors():  # AC-1
    rs = rules(R("a", approvers=frozenset({"x"})), R("a/b", approvers=frozenset({"y"})))
    assert eligible_approvers("a/b/c/f.go", rs, {}) == {"x", "y"}


def test_no_parent_owners_stops_inheritance():  # AC-2
    rs = rules(R("a", approvers=frozenset({"x"})), R("a/b", approvers=frozenset({"y"}), no_parent_owners=True))
    assert eligible_approvers("a/b/c/f.go", rs, {}) == {"y"}


def test_alias_expands_to_members():  # AC-3
    rs = rules(R("a", approvers=frozenset({"sig-node-approvers"})))
    assert eligible_approvers("a/f.go", rs, {"sig-node-approvers": ["p", "q"]}) == {"p", "q"}


def test_author_excluded_from_candidates_and_truth():  # AC-4
    ranked = rank_approvers({"x", "y"}, [Approval("x", d(2026, 9, 1), "a")], author="x", now=d(2026, 9, 10))
    assert [r.login for r in ranked] == ["y"]


def test_recent_subtree_approvals_rank_higher():  # AC-5
    ap = [Approval("x", d(2026, 9, 1 + i), "a/b") for i in range(5)]
    ranked = rank_approvers({"x", "y"}, ap, author="z", now=d(2026, 9, 20))
    assert [r.login for r in ranked] == ["x", "y"]
    assert ranked[0].score > ranked[1].score == 0


def test_hit_at_k():  # AC-6
    assert hit_at_k(["x", "y", "z"], {"z"}, 1) == 0
    assert hit_at_k(["x", "y", "z"], {"z"}, 3) == 1


def test_orphaned_decision_detected():  # AC-8
    keps = [KepRecord(1, "a", "sig-a", "implementable", approvers=frozenset({"gone"})),
            KepRecord(2, "b", "sig-a", "implementable", approvers=frozenset({"gone", "here"})),
            KepRecord(3, "c", "sig-a", "implemented", approvers=frozenset({"gone"}))]
    assert [k.number for k in orphaned_decisions(keps, current_roles={"here"})] == [1]


def test_pii_filter_keeps_login_only():  # AC-9
    assert filter_person({"github": "alice", "name": "Alice A", "company": "X", "email": "a@x.io"}) == {"login": "alice"}


def bot(body, at=1): return Comment("k8s-ci-robot", body, d(2026, 9, at))


def test_approval_notifier_parser_last_approved_wins():  # AC-10
    c1 = bot("[APPROVALNOTIFIER] This PR is **APPROVED**\n\nThis pull-request has been approved by: *a*, *b*\n", 1)
    c2 = bot("[APPROVALNOTIFIER] This PR is **APPROVED**\n\nThis pull-request has been approved by: *a*(Author self-approved), *c*\n", 2)
    c3 = bot("[APPROVALNOTIFIER] This PR is **NOT APPROVED**\n\nThis pull-request has been approved by: *zzz*\n", 3)
    assert parse_approval_notifier([c1, c2, c3], pr_author="a") == {"c"}


def test_owners_health_is_per_file_not_person():  # AC-21
    h = owners_health("pkg/x", listed={"a", "b", "c", "d"}, active={"a"})
    assert h.ratio == 0.25 and h.path == "pkg/x"
    assert set(h.__dataclass_fields__) == {"path", "listed", "active", "ratio"}
    assert not any(isinstance(v, (set, frozenset, list, tuple)) for v in vars(h).values())


# ---- boundary ----
def test_empty_owners_file_yields_no_approvers():
    assert eligible_approvers("a/f.go", rules(R("a")), {}) == frozenset()


def test_cyclic_alias_terminates():
    al = {"a-team": ["b-team", "u1"], "b-team": ["a-team", "u2"]}
    assert expand_aliases(["a-team"], al) == {"u1", "u2"}


def test_root_path_uses_root_owners():
    assert eligible_approvers("README.md", rules(R("", approvers=frozenset({"root"}))), {}) == {"root"}


def test_deleted_directory_falls_back_to_nearest_ancestor():
    rs = rules(R("pkg", approvers=frozenset({"p"})))
    assert eligible_approvers("pkg/removed/dir/f.go", rs, {}) == {"p"}


def test_unknown_path_without_any_rules_is_empty():
    assert eligible_approvers("zzz/f.go", {}, {}) == frozenset()


def test_pii_filter_missing_login_returns_none():
    assert filter_person({"name": "No Handle"}) is None


def test_hit_at_k_empty_truth_is_zero_and_mrr():
    assert hit_at_k(["x"], set(), 3) == 0
    assert mrr(["x", "y"], {"y"}) == 0.5 and mrr(["x"], {"q"}) == 0.0


def test_ranking_without_history_is_deterministic_alphabetical():
    ranked = rank_approvers({"b", "a"}, [], author="z", now=d(2026, 9, 1))
    assert [r.login for r in ranked] == ["a", "b"]


def test_ranking_half_life_decay():
    old = [Approval("x", d(2026, 3, 1), "a")]
    new = [Approval("y", d(2026, 9, 1), "a")]
    ranked = rank_approvers({"x", "y"}, old + new, author="z", now=d(2026, 9, 2))
    assert ranked[0].login == "y"


def test_notifier_ignores_non_bot_authors_and_self_only_is_empty():
    fake = Comment("someone", "This pull-request has been approved by: *evil*", d(2026, 9, 1))
    self_only = bot("This PR is **APPROVED**\n\nThis pull-request has been approved by: *a*(Author self-approved)\n")
    assert parse_approval_notifier([fake], "a") == frozenset()
    assert parse_approval_notifier([self_only], "a") == frozenset()


def test_notifier_handles_html_link_names():
    c = bot('**APPROVED**\n\nThis pull-request has been approved by: <a href="https://github.com/x">dims</a>, *liggitt*\n')
    assert parse_approval_notifier([c], "z") == {"dims", "liggitt"}


def test_owners_health_zero_listed_is_zero_not_error():
    assert owners_health("p", listed=set(), active=set()).ratio == 0.0


def test_kep_with_missing_fields_still_constructs():
    k = KepRecord(9, "t", None, None, approvers=frozenset())
    assert orphaned_decisions([k], current_roles=set()) == []  # no recorded approvers -> nothing to orphan


def test_drift_summary_aggregates_without_naming_people():
    from ownergraph.domain.health import summarize_drift
    s = summarize_drift({"a": {"x", "y"}, "b": {"y", "z"}, "c": set()}, active={"x"})
    assert s.unique_approvers == 3 and s.inactive_approvers == 2 and round(s.inactive_share, 3) == 0.667
    assert [h.path for h in s.files] == ["a", "b", "c"] and s.files[0].ratio == 0.5
    assert not any(isinstance(v, (set, frozenset, list, tuple)) for h in s.files for v in vars(h).values())
    assert summarize_drift({}, set()).inactive_share == 0.0
