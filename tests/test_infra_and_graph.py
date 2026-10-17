import json
import pytest
from ownergraph.infrastructure.readme_numbers import ReadmeMismatch, check_readme, render_numbers_block
from ownergraph.domain.model import PullRequest
from ownergraph.domain.orphans import KepRecord
from tests.fakes import d

RESULTS = {"e1": {"n_eval": 100, "methods": {"graph": {"all": {"hit@3": 0.8}}, "owners_history": {"all": {"hit@3": 0.7}}}},
           "tests": {"passed": 52, "total": 52}}


def test_readme_numbers_match_results():  # AC-18
    block = render_numbers_block(RESULTS)
    readme = f"# x\n<!-- numbers:start -->\n{block}\n<!-- numbers:end -->\n"
    check_readme(readme, RESULTS)
    with pytest.raises(ReadmeMismatch):
        check_readme(readme.replace("80.0%", "81.0%"), RESULTS)
    with pytest.raises(ReadmeMismatch):
        check_readme("# no block", RESULTS)


@pytest.fixture()
def repo(tmp_path):
    from ownergraph.adapters.falkordb_repository import FalkorRepository
    r = FalkorRepository.embedded(str(tmp_path / "g.db"), graph="t")
    from ownergraph.domain.owners import OwnersRule
    r.load_owners({"pkg": OwnersRule("pkg", approvers=frozenset({"x", "grp"})),
                   "pkg/a": OwnersRule("pkg/a", approvers=frozenset({"y"}), no_parent_owners=False)},
                  aliases={"grp": ["m1", "m2"]})
    r.upsert_prs([PullRequest(1, "t", "", "au", d(2026, 9, 1), ("pkg/a/f.go",), ("sig/node",), frozenset({"y"})),
                  PullRequest(2, "t2", "", "au", d(2026, 9, 5), ("pkg/b/g.go",), ("sig/node",), frozenset({"m1"}))])
    r.upsert_keps([KepRecord(7, "Sidecar", "sig-node", "implementable", approvers=frozenset({"zed"}), feature_gates=("SidecarContainers",))])
    return r


def test_falkordb_contract_roundtrip(repo):  # integration (embedded FalkorDB, no docker)
    rows = repo.eligible_approvers("pkg/a/f.go").rows
    assert {r["login"] for r in rows} == {"x", "m1", "m2", "y"}
    dec = repo.deciders("pkg/a/f.go").rows
    assert dec and dec[0]["login"] == "y"
    assert repo.deciders("pkg/a/f.go", cutoff=d(2026, 8, 1)).rows == []  # cutoff hides later approvals


def test_decision_trail_uses_graph_path(repo):
    r = repo.decision_trail("SidecarContainers")
    assert r.rows[0]["kep"] == 7 and r.rows[0]["sig"] == "sig-node" and "INTRODUCES" in r.cypher


def test_stale_decisions_from_graph(repo):
    r = repo.stale_decisions()
    assert [x["kep"] for x in r.rows] == [7]  # zed holds no current approver role


def test_repository_refuses_write_cypher_on_read_path(repo):
    from ownergraph.adapters.readonly_guard import WriteQueryRejected
    with pytest.raises(WriteQueryRejected):
        repo.run_read("MATCH (n) DETACH DELETE n")


def test_eligible_walk_passes_through_directories_without_owners(repo):
    # regression: intermediate directories that have no OWNERS file (null npo) must not break the walk
    repo.upsert_prs([PullRequest(3, "deep", "", "au", d(2026, 9, 6), ("pkg/a/deep/x/f.go",), (), frozenset({"y"}))])
    repo.link_directory_tree()
    assert {r["login"] for r in repo.eligible_approvers("pkg/a/deep/x/f.go").rows} == {"x", "m1", "m2", "y"}


def test_deciders_report_tiers_near_before_scope(repo):
    rows = repo.deciders("pkg/a/f.go").rows
    assert rows[0]["tier"] == "self" and all(r["tier"] in {"self", "scope", "nearby", "ancestor", "sig"} for r in rows)


def test_no_parent_owners_boundary_inclusive_in_graph(tmp_path):
    # regression: the OWNERS node at the boundary directory must not count as a blocking node on the walk
    from ownergraph.adapters.falkordb_repository import FalkorRepository
    from ownergraph.domain.owners import OwnersRule
    r = FalkorRepository.embedded(str(tmp_path / "b.db"), graph="b")
    r.load_owners({"": OwnersRule("", approvers=frozenset({"root"})),
                   "lib": OwnersRule("lib", approvers=frozenset({"libowner"}), no_parent_owners=True)}, aliases={})
    r.upsert_prs([PullRequest(1, "t", "", "au", d(2026, 9, 1), ("lib/x/y/f.go",), (), frozenset({"libowner"}))])
    r.link_directory_tree()
    assert {x["login"] for x in r.eligible_approvers("lib/x/y/f.go").rows} == {"libowner"}


def test_ownership_edges_nearest_owner_and_parent_chain(repo):
    repo.link_ownership()
    under = {r["d"]: r["o"] for r in repo.run_read("MATCH (d:Directory)-[:UNDER]->(o:OwnersFile) RETURN d.path AS d, o.path AS o")}
    assert under["pkg/a"] == "pkg/a" and under["pkg/b"] == "pkg"
    par = [(r["c"], r["p"]) for r in repo.run_read("MATCH (c:OwnersFile)-[:PARENT_OWNERS]->(p:OwnersFile) RETURN c.path AS c, p.path AS p")]
    assert par == [("pkg/a", "pkg")]


def test_parent_owners_edge_respects_no_parent_owners(tmp_path):
    from ownergraph.adapters.falkordb_repository import FalkorRepository
    from ownergraph.domain.owners import OwnersRule
    r = FalkorRepository.embedded(str(tmp_path / "p.db"), graph="p")
    r.load_owners({"a": OwnersRule("a", approvers=frozenset({"x"})),
                   "a/b": OwnersRule("a/b", approvers=frozenset({"y"}), no_parent_owners=True)}, aliases={})
    r.link_ownership()
    assert r.run_read("MATCH (:OwnersFile)-[e:PARENT_OWNERS]->(:OwnersFile) RETURN count(e) AS c")[0]["c"] == 0


def test_kep_deciders_follow_implements_edge_and_respect_cutoff(repo):
    repo.upsert_prs([PullRequest(9, "KEP-7 step", "", "au", d(2026, 9, 10), ("x/y.go",), (), frozenset({"zed2"}), kep_refs=(7,))])
    rows = repo.kep_deciders(7, cutoff=d(2026, 10, 1)).rows
    assert [r["login"] for r in rows] == ["zed2"] and rows[0]["tier"] == "kep"
    assert repo.kep_deciders(7, cutoff=d(2026, 9, 1)).rows == []


def test_numbers_block_includes_e2_and_selected_e1_segments():
    res = {"e1": {"n_eval": 10, "methods": {"graph": {"all": {"hit@3": 0.5, "hit@1": 0.25, "n": 10}, "easy": {"hit@3": 0.1, "hit@1": 0.1, "n": 1}}}},
           "e2": {"n": {"single": 2, "multi": 3}, "systems": {"graph": {"single": 1.0, "multi": 0.9}, "rag": {"single": 1.0, "multi": 0.3}},
                  "ablation_multi_drop_pp": 60.0}}
    block = render_numbers_block(res)
    assert "E2 graph [multi-hop, n=3] accuracy: 90.0%" in block and "E2 rag [multi-hop, n=3] accuracy: 30.0%" in block
    assert "[easy]" not in block and "[all]" in block


def test_datafiles_reads_plain_or_gzipped(tmp_path):
    from ownergraph.infrastructure.datafiles import read_text, write_gz
    (tmp_path / "a.txt").write_text("plain")
    write_gz(tmp_path, "b.txt", "zipped")
    assert read_text(tmp_path, "a.txt") == "plain" and read_text(tmp_path, "b.txt") == "zipped"


def test_repo_drift_inputs_from_graph(repo):
    listing = repo.owners_listing()
    assert listing["pkg"] == {"x", "m1", "m2"} and listing["pkg/a"] == {"y"}
    assert repo.active_approvers(since=d(2026, 9, 3)) == {"m1"}   # y approved on 9/1 (too old), m1 on 9/5
    assert repo.active_approvers(since=d(2026, 8, 1)) == {"y", "m1"}


def test_route_candidates_pick_sig_and_approvers_by_actual_activity(tmp_path):
    from ownergraph.adapters.falkordb_repository import FalkorRepository
    from ownergraph.domain.owners import OwnersRule
    r = FalkorRepository.embedded(str(tmp_path / "r.db"), graph="r")
    r.load_owners({"pkg/kubelet": OwnersRule("pkg/kubelet", approvers=frozenset({"k1", "k2", "k3"}), labels=frozenset({"sig/node"})),
                   "pkg/apiserver": OwnersRule("pkg/apiserver", approvers=frozenset({"a1"}), labels=frozenset({"sig/api-machinery"})),
                   "pkg": OwnersRule("pkg", approvers=frozenset({"boss"})),
                   # many quiet OWNERS dirs whose names also contain "apiserver": file count alone would pick sig-auth
                   **{f"auth/apiserver-{i}": OwnersRule(f"auth/apiserver-{i}", approvers=frozenset({"z"}), labels=frozenset({"sig/auth"})) for i in range(3)}}, aliases={})
    r.upsert_keps([KepRecord(5, "kubelet thing", "sig-node", "implementable", approvers=frozenset({"k1"})),
                   KepRecord(6, "done", "sig-node", "implemented", approvers=frozenset({"k1"}))])
    r.upsert_prs([PullRequest(i, "t", "", "au", d(2026, 9, i), ("pkg/kubelet/x.go",), (), frozenset(a)) for i, a in
                  [(1, {"k1", "boss"}), (2, {"k1"}), (3, {"k2"}), (5, {"k2"})]] +
                 [PullRequest(4, "t", "", "au", d(2026, 9, 4), ("pkg/apiserver/y.go",), (), frozenset({"a1", "boss", "k1"}))])
    r.link_directory_tree(); r.link_ownership(); r.mark_current({"k1", "k2", "a1", "boss"})
    row = r.route_candidates(["kubelet"]).rows[0]
    assert row["sig"] == "sig-node" and row["approvers"][:2] == ["k1", "k2"] and row["keps"] == [5]
    assert r.route_candidates(["apiserver"]).rows[0]["sig"] == "sig-api-machinery"
    assert r.route_candidates(["zzz-nothing"]).rows == []


def test_numbers_block_includes_paired_difference_with_ci():
    res = {"e1": {"n_eval": 5, "methods": {}, "paired_graph_minus_owners_history_hit3": {"hard": {"n": 3, "diff": 0.05, "ci95": [0.01, 0.09]}, "easy": {"n": 2, "diff": 0.0, "ci95": [0.0, 0.0]}}}}
    block = render_numbers_block(res)
    assert "E1 graph minus owners_history [hard] hit@3: +5.0 pp (95% CI +1.0 to +9.0, n=3)" in block and "[easy]" not in block
