"""Core value objects. Stdlib only: the domain knows no framework, SDK or I/O."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Comment:
    author: str
    body: str
    created_at: datetime


@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    body: str
    author: str
    merged_at: datetime
    files: tuple = ()
    labels: tuple = ()
    approvers: frozenset = frozenset()  # actual non-author approvers (APPROVALNOTIFIER)
    comments: tuple = ()
    kep_refs: tuple = ()
    url: str = ""
