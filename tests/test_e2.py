import json
from ownergraph.application.eval_e2 import Question, grade, run_e2, extract_list
from ownergraph.application.e2_agents import GraphAgent, RagAgent, tfidf_chunks
from tests.fakes import FakeLlm, FakeRepo


def q(kind="multi", typ="gate_approvers", key=("a", "b"), mode="set"):
    return Question("q1", kind, typ, "who?", frozenset(key), mode)


def test_extract_list_handles_fences_and_prose():
    assert extract_list('```json\n["a", "b"]\n```') == ["a", "b"]
    assert extract_list('The answer is ["x"]. Thanks') == ["x"]
    assert extract_list("no list here") == []


def test_grade_set_requires_exact_match_case_insensitive():
    assert grade(q(), '["B", "a"]') and not grade(q(), '["a"]') and not grade(q(), '["a","b","c"]')


def test_grade_member_mode_accepts_any_correct_subset_but_no_wrong_names():
    m = q(mode="member", key=("a", "b", "c"))
    assert grade(m, '["b"]') and not grade(m, '["b", "zzz"]') and not grade(m, "[]")


def test_run_e2_reports_by_kind_and_type_and_ablation_drop():
    qs = [q("single", "kep_sig", ("s",)), q("multi", "gate_approvers", ("a",)), q("multi", "gate_approvers", ("b",))]
    good = lambda question: json.dumps(sorted(question.key))
    bad = lambda question: "[]"
    r = run_e2(qs, {"graph": good, "rag": lambda x: good(x) if x.kind == "single" else bad(x)})
    assert r["n"] == {"single": 1, "multi": 2} and r["systems"]["graph"]["multi"] == 1.0 and r["systems"]["rag"]["multi"] == 0.0
    assert r["ablation_multi_drop_pp"] == 100.0


def test_graph_agent_plans_then_answers_from_rows_only():
    repo = FakeRepo()
    llm = FakeLlm(replies=['{"tool": "explain_feature_gate", "arg": "SidecarContainers"}', '["dchen1107"]'])
    out = GraphAgent(repo, llm).answer("Who approved the KEP behind SidecarContainers?")
    assert out == '["dchen1107"]' and "dchen1107" in llm.calls[1]  # rows were handed to the answering call
    assert llm.calls[0].count("SidecarContainers") >= 1


def test_graph_agent_abstains_without_rows():
    repo = FakeRepo(); repo.trail_rows = []
    llm = FakeLlm(replies=['{"tool": "explain_feature_gate", "arg": "Nope"}'])
    assert GraphAgent(repo, llm).answer("?") == "[]" and len(llm.calls) == 1  # no rows -> no answer call


def test_rag_agent_retrieves_relevant_chunk():
    chunks = [("kep:1", "title: Sidecar containers feature SidecarContainers approvers: dchen1107"),
              ("kep:2", "title: Unrelated storage thing approvers: someoneelse")]
    llm = FakeLlm(replies=['["dchen1107"]'])
    RagAgent(tfidf_chunks(chunks), llm, k=1).answer("Who approved SidecarContainers?")
    assert "dchen1107" in llm.calls[0] and "someoneelse" not in llm.calls[0]


def test_run_e2_aborts_when_a_system_mostly_errors():
    import pytest
    from ownergraph.application.eval_e2 import SystemicFailure
    qs = [q("multi", "t", ("a",)) for _ in range(8)]
    def boom(question): raise RuntimeError("HTTP 404")
    with pytest.raises(SystemicFailure):
        run_e2(qs, {"graph": boom})


def test_grade_ignores_at_prefix_and_retriever_matches_kep_numbers_and_paths():
    assert grade(q(key=("liggitt",)), '["@liggitt"]')
    r = tfidf_chunks([("kep:keps/sig-node/753-sidecar/kep.yaml", "title: Sidecar\nkep-number: 753\nstatus: implemented"),
                      ("owners:pkg/registry/scheduling/OWNERS", "approvers:\n- alice"),
                      ("kep:other", "kep-number: 9")])
    assert r.search("Which SIG owns KEP-753?", 1)[0][0].startswith("kep:keps/sig-node/753")
    assert r.search("approve pkg/registry/scheduling/example_test.go", 1)[0][0].startswith("owners:pkg/registry/scheduling")
