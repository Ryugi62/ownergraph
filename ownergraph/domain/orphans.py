from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

CLOSED = {"implemented", "withdrawn", "replaced", "rejected"}


@dataclass(frozen=True)
class KepRecord:
    number: int
    title: str
    owning_sig: Optional[str]
    status: Optional[str]
    approvers: frozenset = frozenset()
    authors: frozenset = frozenset()
    participating_sigs: tuple = ()
    feature_gates: tuple = ()
    stage: Optional[str] = None
    milestone: Optional[dict] = None
    updated_at: Optional[datetime] = None
    url: str = ""


def orphaned_decisions(keps, current_roles) -> list:
    """AC-8: a KEP whose recorded approvers hold no current approver role."""
    roles = set(current_roles)
    return [k for k in keps
            if (k.status or "") not in CLOSED and k.approvers and not (set(k.approvers) & roles)]
