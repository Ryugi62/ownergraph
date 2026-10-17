import json
from ownergraph.adapters.parsers import parse_aliases, parse_kep, parse_owners, parse_pr, parse_sig_leaders


def test_owners_options_and_filters_and_garbage():
    r = parse_owners("a", "approvers:\n- x\n- '@y'\noptions:\n  no_parent_owners: true\nlabels:\n- sig/node\n")
    assert r.approvers == {"x", "y"} and r.no_parent_owners and r.labels == {"sig/node"}
    assert parse_owners("a", "filters:\n  '.*':\n    approvers: [z]\n").approvers == {"z"}
    assert parse_owners("a", ":::not yaml:::[").approvers == frozenset()
    assert parse_owners("a", "").approvers == frozenset()


def test_kep_with_impossible_date_still_parses():
    k = parse_kep("title: T\nkep-number: 12\nowning-sig: sig-a\nstatus: provisional\ncreation-date: 2026-13-45\n"
                  "approvers:\n- '@dims'\nfeature-gates:\n- name: Foo\n", "keps/sig-a/12-t/kep.yaml")
    assert k.number == 12 and k.approvers == {"dims"} and k.feature_gates == ("Foo",)


def test_kep_number_from_path_when_missing():
    assert parse_kep("title: T\n", "keps/sig-a/345-name/kep.yaml").number == 345
    assert parse_kep("title: T\n", "keps/sig-a/readme/kep.yaml") is None


def test_sig_leaders_drop_pii():
    y = "sigs:\n- dir: sig-a\n  leadership:\n    chairs:\n    - {github: c1, name: Real Name, company: X}\n    tech_leads:\n    - {github: t1, name: N}\n"
    assert parse_sig_leaders(y) == {"sig-a": [("c1", "CHAIRS"), ("t1", "LEADS")]}


def test_aliases_and_pr_node():
    assert parse_aliases("aliases:\n  g:\n  - a\n  - '@b'\n") == {"g": ["a", "b"]}
    node = {"number": 5, "title": "KEP-1234: do thing", "bodyText": "", "url": "u", "mergedAt": "2026-09-01T00:00:00Z",
            "author": {"login": "au"}, "labels": {"nodes": []}, "files": {"nodes": [{"path": "pkg/a.go"}]},
            "comments": {"nodes": [{"author": {"login": "kubernetes-prow"}, "createdAt": "2026-09-01T01:00:00Z",
                                    "body": "[APPROVALNOTIFIER] This PR is **APPROVED**\n\nThis pull-request has been approved by: *bob*\n"}]}}
    pr = parse_pr(node)
    assert pr.approvers == {"bob"} and pr.kep_refs == (1234,) and pr.files == ("pkg/a.go",)
