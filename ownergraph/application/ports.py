"""Ports: the application depends on these, adapters implement them."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol


@dataclass
class QueryResult:
    cypher: str
    params: dict
    rows: list
    urls: list = field(default_factory=list)


class GraphRepository(Protocol):
    def eligible_approvers(self, path: str) -> QueryResult: ...
    def deciders(self, path: str, cutoff: Optional[datetime] = None) -> QueryResult: ...
    def decision_trail(self, key: str) -> QueryResult: ...
    def route_candidates(self, entities: list) -> QueryResult: ...
    def stale_decisions(self, sig: Optional[str] = None) -> QueryResult: ...
    def find_entity(self, name: str) -> QueryResult: ...


class LlmClient(Protocol):
    def complete(self, prompt: str) -> str: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class SourceFetcher(Protocol):
    def keps_since(self, since: Optional[datetime]) -> list: ...
    def prs_since(self, since: Optional[datetime]) -> list: ...
