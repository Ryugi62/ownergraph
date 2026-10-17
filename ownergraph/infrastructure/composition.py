"""Composition root: the only place that knows concrete adapters."""
from __future__ import annotations
import os
from datetime import datetime, timezone

from ..adapters.falkordb_repository import FalkorRepository
from ..application.ask import AskService


class SystemClock:
    def now(self):
        return datetime.now(timezone.utc)


class NoLlm:
    def complete(self, prompt: str) -> str:
        raise RuntimeError("no LLM configured (set GEMINI_API_KEY)")


def make_repo(graph: str = "org:kubernetes"):
    host = os.environ.get("FALKORDB_HOST")
    if host:
        return FalkorRepository.remote(host, int(os.environ.get("FALKORDB_PORT", "6379")), graph)
    return FalkorRepository.embedded(os.environ.get("OWNERGRAPH_DB", "data/ownergraph.db"), graph)


def make_llm():
    if os.environ.get("GEMINI_API_KEY"):
        from ..adapters.gemini_llm import GeminiLlm
        return GeminiLlm()
    return NoLlm()


def build_services(graph: str = "org:kubernetes"):
    repo, llm = make_repo(graph), make_llm()
    return AskService(repo, llm, SystemClock()), repo, llm
