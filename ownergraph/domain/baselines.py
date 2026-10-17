"""Non-graph baselines for E1 (pure, in-memory). They see exactly what the graph method sees: OWNERS snapshot + pre-cutoff PRs."""
from __future__ import annotations
import math, random, re
from collections import defaultdict
from datetime import datetime

from .owners import OwnersRule, ancestors, eligible_approvers


def governing_dir(file_path: str, rules: dict) -> str | None:
    for d in ancestors(file_path):
        if d in rules:
            return d
    return None


class ProwRandom:
    """(a) Prow-style: eligible approvers of the changed files, greedy set cover with random tie-breaking."""
    def __init__(self, rules, aliases, seed=7):
        self.rules, self.aliases, self.seed = rules, aliases, seed

    def predict(self, feats, k=10):
        files = feats["files"]
        per_file = {f: set(eligible_approvers(f, self.rules, self.aliases)) for f in files}
        rng = random.Random(self.seed + len(files) + sum(map(len, files)))
        chosen, uncovered = [], {f for f, e in per_file.items() if e}
        pool = sorted(set().union(*per_file.values())) if per_file else []
        while uncovered and pool and len(chosen) < k:
            rng.shuffle(pool)
            best = max(pool, key=lambda a: sum(1 for f in uncovered if a in per_file[f]))
            chosen.append(best)
            uncovered = {f for f in uncovered if best not in per_file[f]}
            pool.remove(best)
        rng.shuffle(pool)
        return chosen + pool[: max(0, k - len(chosen))]


class OwnersHistory:
    """(e) per-OWNERS-file approval counts with recency decay (strongest non-graph baseline)."""
    def __init__(self, rules, aliases, train, now: datetime, half_life=90.0):
        self.rules, self.aliases, self.now, self.hl = rules, aliases, now, half_life
        self.table = defaultdict(lambda: defaultdict(float))
        for pr in train:
            age = max((now - pr.merged_at).total_seconds() / 86400, 0)
            w = 0.5 ** (age / half_life)
            for d in {governing_dir(f, rules) for f in pr.files} - {None}:
                for a in pr.approvers - {pr.author}:
                    self.table[d][a] += w
        self.fallback = ProwRandom(rules, aliases)

    def dirs_of(self, feats):
        return {governing_dir(f, self.rules) for f in feats["files"]} - {None}

    def has_history(self, feats) -> bool:
        return any(self.table.get(d) for d in self.dirs_of(feats))

    def predict(self, feats, k=10):
        elig = set()
        for f in feats["files"]:
            elig |= eligible_approvers(f, self.rules, self.aliases)
        score = defaultdict(float)
        for d in self.dirs_of(feats):
            for a, s in self.table.get(d, {}).items():
                if a in elig:
                    score[a] += s
        ranked = [a for a, _ in sorted(score.items(), key=lambda x: (-x[1], x[0]))]
        return (ranked + [a for a in self.fallback.predict(feats, k) if a not in ranked])[:k]


_TOK = re.compile(r"[a-z0-9]+")


def _tokens(feats) -> list:
    text = feats["title"].lower() + " " + " ".join(feats["files"]).lower().replace("/", " ").replace("_", " ").replace(".", " ")
    return _TOK.findall(text)


class TfidfRetrieval:
    """(b) vector-RAG stand-in: tf-idf cosine over past PRs (title + changed paths); vote the approvers of the nearest PRs."""
    def __init__(self, train, now: datetime, k_neighbors=15):
        self.docs, self.k = [], k_neighbors
        df = defaultdict(int)
        toks = []
        for pr in train:
            t = _tokens({"title": pr.title, "files": pr.files})
            toks.append(t)
            for w in set(t):
                df[w] += 1
        n = max(len(train), 1)
        self.idf = {w: math.log((n + 1) / (c + 1)) + 1 for w, c in df.items()}
        for pr, t in zip(train, toks):
            v = self._vec(t)
            age = max((now - pr.merged_at).total_seconds() / 86400, 0)
            self.docs.append((v, pr.approvers - {pr.author}, 0.5 ** (age / 90)))

    def _vec(self, toks):
        tf = defaultdict(float)
        for w in toks:
            if w in self.idf:
                tf[w] += self.idf[w]
        norm = math.sqrt(sum(x * x for x in tf.values())) or 1.0
        return {w: x / norm for w, x in tf.items()}

    def predict(self, feats, k=10):
        q = self._vec(_tokens(feats))
        sims = sorted(((sum(q.get(w, 0) * x for w, x in v.items()), ap, rec) for v, ap, rec in self.docs), key=lambda t: -t[0])[: self.k]
        score = defaultdict(float)
        for s, ap, rec in sims:
            for a in ap:
                score[a] += s * rec
        return [a for a, _ in sorted(score.items(), key=lambda x: (-x[1], x[0]))][:k]
