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
