"""Wires E2: frozen questions x {graph agent, vector-RAG agent, LLM alone}, same LLM."""
from __future__ import annotations
import json
from pathlib import Path

import yaml

from ..adapters.falkordb_repository import FalkorRepository
from ..adapters.gemini_llm import GeminiLlm
from ..application.e2_agents import ANSWER, GraphAgent, RagAgent, tfidf_chunks
from ..application.eval_e2 import Question, run_e2


class LlmOnly:
    def __init__(self, llm):
        self.llm = llm

    def answer(self, question):
        return self.llm.complete(ANSWER + f"Question: {question}\n(No data is provided; answer from memory or reply [].)")


def build_chunks(raw: Path) -> list:
    chunks = []
    for path, text in json.loads((raw / "keps.json").read_text()).items():
        chunks.append((f"kep:{path}", text[:2500]))
    files = json.loads((raw / "owners_at_head.json").read_text())
    for path, text in files.items():
        if path.endswith("OWNERS"):
            chunks.append((f"owners:{path}", text[:1500]))
    aliases = (yaml.safe_load(files["OWNERS_ALIASES"]) or {}).get("aliases") or {}
    for name, members in aliases.items():
        chunks.append((f"alias:{name}", f"alias {name} members: {', '.join(str(m) for m in members or [])}"))
    for s in (yaml.safe_load((raw / "sigs.yaml").read_text()) or {}).get("sigs", []):
        lead = s.get("leadership") or {}
        handles = {k: [p.get("github") for p in (lead.get(k) or []) if p.get("github")] for k in ("chairs", "tech_leads")}
        chunks.append((f"sig:{s.get('dir')}", f"SIG {s.get('dir')} ({s.get('name')}) chairs: {', '.join(handles['chairs'])}; "
                                              f"tech leads: {', '.join(handles['tech_leads'])}"))
    return chunks


def load_questions(path: Path) -> list:
    return [Question(q["id"], q["kind"], q["type"], q["text"], frozenset(q["key"]), q["mode"]) for q in json.loads(path.read_text())]


def run(raw: Path, qpath: Path, db: str, out: Path, interval: float = 4.5, log=print) -> dict:
    llm = GeminiLlm(min_interval=interval)
    repo = FalkorRepository.embedded(db, graph="org:kubernetes")
    chunks = build_chunks(raw)
    agents = {"graph": GraphAgent(repo, llm), "rag": RagAgent(tfidf_chunks(chunks), llm), "llm_only": LlmOnly(llm)}
    qs = load_questions(qpath)
    done = {"n": 0}

    def wrap(agent):
        def fn(q):
            a = agent.answer(q.text)
            done["n"] += 1
            if done["n"] % 10 == 0:
                log(f"{done['n']} answers", flush=True)
            return a
        return fn

    res = run_e2(qs, {name: wrap(a) for name, a in agents.items()})
    res["llm"] = llm.model
    res["rag"] = {"retriever": "tf-idf cosine", "chunks": len(chunks), "k": 6}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2))
    return res
