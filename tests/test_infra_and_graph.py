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
