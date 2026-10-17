import asyncio
import pytest
from fastapi.testclient import TestClient
from ownergraph.adapters.readonly_guard import WriteQueryRejected, assert_read_only
from ownergraph.adapters.mcp_server import build_server, TOOL_NAMES
from ownergraph.adapters.http_api import create_app
from ownergraph.application.ask import AskService
from tests.fakes import FakeClock, FakeLlm, FakeRepo, d


@pytest.mark.parametrize("q", ["CREATE (n:X)", "MATCH (n) DELETE n", "MATCH (n) SET n.a=1",
                               "MERGE (n:X)", "MATCH (n) REMOVE n.a", "match (n) detach delete n",
                               "MATCH (n) RETURN n; CREATE (m)", "CALL db.idx.fulltext.createNodeIndex('X')"])
def test_readonly_guard_rejects_writes(q):  # AC-15
    with pytest.raises(WriteQueryRejected):
        assert_read_only(q)


def test_readonly_guard_allows_reads_and_keywords_in_strings():
    assert_read_only("MATCH (n:Person {login:'create'}) RETURN n LIMIT 3")
    assert_read_only("MATCH (a)-[:CHILD_OF*0..]->(b) WHERE a.path = 'SET DELETE' RETURN b")


def test_mcp_lists_six_tools():  # AC-16
    server = build_server(AskService(FakeRepo(), FakeLlm(), FakeClock(d(2026, 10, 1))), FakeRepo(), FakeLlm())
    tools = asyncio.run(server.list_tools())
    assert sorted(t.name for t in tools) == sorted(["find_entity", "approvers_for_path", "deciders_for_path",
                                                    "explain_feature_gate", "route_issue", "stale_decisions"])
    assert set(TOOL_NAMES) == {t.name for t in tools}
    assert all(t.inputSchema.get("properties") is not None for t in tools)


def client():
    app = create_app(AskService(FakeRepo(), FakeLlm(), FakeClock(d(2026, 10, 1))))
    return TestClient(app)


def test_api_ask_returns_evidence_path():  # AC-17
    r = client().post("/api/ask", json={"question": "who approves pkg/kubelet/kubelet.go ?"})
    assert r.status_code == 200
    j = r.json()
    assert j["evidence"]["cypher"] and j["evidence"]["urls"] and j["abstained"] is False
    assert r.elapsed.total_seconds() <= 1


def test_api_abstains_with_200_and_reason():
    repo = FakeRepo(); repo.eligible_rows = []
    c = TestClient(create_app(AskService(repo, FakeLlm(), FakeClock(d(2026, 10, 1)))))
    j = c.post("/api/ask", json={"question": "who approves pkg/x/y.go ?"}).json()
    assert j["abstained"] is True and j["evidence"]["cypher"]


def test_api_rejects_empty_question():
    assert client().post("/api/ask", json={"question": "  "}).status_code == 422


def test_ui_answer_card_order():  # UI 수용기준
    html = open("ownergraph/adapters/web/index.html", encoding="utf-8").read()
    order = [html.index(f'id="{i}"') for i in ("question", "chips", "answer-sentence", "path-graph", "cypher-panel", "sources")]
    assert order == sorted(order)
    assert html.count('class="chip"') == 3 and 'id="loading"' in html and "Querying the graph" in html
