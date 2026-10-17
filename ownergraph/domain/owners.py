"""OwnersResolver: inheritance, aliases, no_parent_owners (AC-1..3)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class OwnersRule:
    path: str  # directory, "" = repository root
    approvers: frozenset = frozenset()
    reviewers: frozenset = frozenset()
    no_parent_owners: bool = False
    labels: frozenset = frozenset()


def expand_aliases(names: Iterable[str], aliases: Mapping[str, Iterable[str]]) -> frozenset:
    out, seen, stack = set(), set(), list(names)
    while stack:
        n = stack.pop()
        if n in aliases:
            if n not in seen:
                seen.add(n)
                stack.extend(aliases[n])
        else:
            out.add(n)
    return frozenset(out)


def ancestors(path: str) -> list:
    """Directories governing `path`, deepest first, ending with the root ''."""
    parts = path.split("/")[:-1]  # drop file name
    return ["/".join(parts[:i]) for i in range(len(parts), -1, -1)]


def eligible_approvers(file_path: str, rules: Mapping[str, OwnersRule], aliases: Mapping[str, Iterable[str]]) -> frozenset:
    out = set()
    for d in ancestors(file_path):
        r = rules.get(d)
        if r is None:
            continue
        out |= expand_aliases(r.approvers, aliases)
        if r.no_parent_owners:
            break
    return frozenset(out)
