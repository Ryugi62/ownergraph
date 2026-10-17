"""The two E2 systems. Same LLM, same question; the only difference is where the facts come from."""
from __future__ import annotations
import json, math, re
from collections import defaultdict

PLAN = ("You answer questions about the Kubernetes project using tools. Pick ONE tool and its argument.\n"
        "Tools: explain_feature_gate(arg = feature gate name OR KEP number like 753) -> KEP, status, owning SIG, KEP approvers, SIG chairs;\n"
        "approvers_for_path(arg = repo file path) -> people allowed to approve changes to that path (OWNERS inheritance and aliases resolved);\n"
        "stale_decisions(arg = '') ; find_entity(arg = name).\n"
        'Reply with JSON only: {"tool": "...", "arg": "..."}\nQuestion: ')
ANSWER = ("Answer using ONLY the data below. Reply with a JSON array of strings and nothing else "
          "(GitHub logins, SIG ids, or a status word, exactly as written in the data).\n")


def _rows_for(repo, tool, arg):
    if tool == "explain_feature_gate":
        return repo.decision_trail(arg)
    if tool == "approvers_for_path":
        return repo.eligible_approvers(arg)
    if tool == "stale_decisions":
        return repo.stale_decisions()
    return repo.find_entity(arg)


class GraphAgent:
    """LLM picks a tool; FalkorDB answers; the LLM only phrases the rows. No rows -> no answer call (abstain)."""
    def __init__(self, repo, llm):
        self.repo, self.llm = repo, llm

    def answer(self, question: str) -> str:
        try:
            plan = json.loads(re.search(r"\{.*\}", self.llm.complete(PLAN + question), re.S).group(0))
            qr = _rows_for(self.repo, plan["tool"], str(plan.get("arg", "")))
        except (ValueError, KeyError, AttributeError, TypeError):  # unparsable plan -> abstain; transport errors propagate
            return "[]"
        if not qr.rows:
            return "[]"
        rows = json.dumps(qr.rows[:60], default=str)
        return self.llm.complete(ANSWER + f"Question: {question}\nGraph rows: {rows}")


_TOK = re.compile(r"[a-z0-9]+")


class Retriever:
    def __init__(self, chunks):
        self.chunks = chunks
        df = defaultdict(int)
        toks = [set(_TOK.findall(f"{c} {t}".lower())) for c, t in chunks]
        for s in toks:
            for w in s:
                df[w] += 1
        n = len(chunks)
        self.idf = {w: math.log((n + 1) / (c + 1)) + 1 for w, c in df.items()}
        self.vecs = [self._vec(f"{c} {t}") for c, t in chunks]

    def _vec(self, text):
        tf = defaultdict(float)
        for w in _TOK.findall(text.lower()):
            if w in self.idf:
                tf[w] += self.idf[w]
        norm = math.sqrt(sum(v * v for v in tf.values())) or 1.0
        return {w: v / norm for w, v in tf.items()}

    def search(self, query: str, k: int):
        q = self._vec(query)
        scored = sorted(((sum(q.get(w, 0) * v for w, v in vec.items()), i) for i, vec in enumerate(self.vecs)), reverse=True)[:k]
        return [self.chunks[i] for s, i in scored if s > 0]


def tfidf_chunks(chunks) -> Retriever:
    return Retriever(chunks)


class RagAgent:
    """Vector-RAG stand-in (tf-idf vectors) over the raw YAML chunks: no graph, no joins."""
    def __init__(self, retriever, llm, k: int = 6):
        self.retriever, self.llm, self.k = retriever, llm, k

    def answer(self, question: str) -> str:
        passages = "\n---\n".join(f"[{cid}]\n{text}" for cid, text in self.retriever.search(question, self.k))
        return self.llm.complete(ANSWER + f"Question: {question}\nPassages:\n{passages}")
