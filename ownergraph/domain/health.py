from dataclasses import dataclass


@dataclass(frozen=True)
class OwnersHealth:
    path: str
    listed: int
    active: int
    ratio: float


def owners_health(path: str, listed, active) -> OwnersHealth:
    """Per-OWNERS-file aggregate only: no per-person field (SPEC non-goal, AC-21)."""
    listed = set(listed)
    n_active = len(listed & set(active))
    return OwnersHealth(path, len(listed), n_active, (n_active / len(listed)) if listed else 0.0)


@dataclass(frozen=True)
class DriftSummary:
    files: tuple
    unique_approvers: int
    inactive_approvers: int
    inactive_share: float


def summarize_drift(listed_by_file: dict, active) -> DriftSummary:
    """UC-9: written authority (OWNERS) vs actual decisions. Aggregates only - no list of inactive people is produced."""
    active = set(active)
    files = tuple(owners_health(p, ls, active) for p, ls in sorted(listed_by_file.items()))
    everyone = set().union(*listed_by_file.values()) if listed_by_file else set()
    inactive = everyone - active
    return DriftSummary(files, len(everyone), len(inactive), (len(inactive) / len(everyone)) if everyone else 0.0)
