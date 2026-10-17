"""FalkorDB adapter. Every answer-path query is a Cypher template run through ro_query (read-only connection)
after the keyword guard. Loading uses a separate write path."""
from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Optional

from ..application.ports import QueryResult
from ..domain.owners import ancestors
from ..domain.orphans import CLOSED
from .readonly_guard import assert_read_only

GH = "https://github.com/kubernetes/kubernetes"
FAR_FUTURE = 4_102_444_800  # 2100-01-01


def _epoch(dt: Optional[datetime]) -> int:
    return int(dt.timestamp()) if dt else FAR_FUTURE


def _iso(ts) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()


Q_ELIGIBLE = """
MATCH (d:Directory) WHERE d.path IN $cands WITH d ORDER BY size(d.path) DESC LIMIT 1
MATCH p=(d)-[:CHILD_OF*0..30]->(a:Directory)<-[:GOVERNS]-(o:OwnersFile)
WHERE NOT any(n IN nodes(p)[0..length(p)] WHERE n.npo = true)
MATCH (u:Person)-[:MEMBER_OF*0..3]->(g)-[:APPROVER_IN]->(o)
RETURN DISTINCT u.login AS login, o.path AS owners_file"""

Q_DECIDERS = """
MATCH (d:Directory) WHERE d.path IN $cands WITH d ORDER BY size(d.path) DESC LIMIT 1
MATCH p1=(d)-[:CHILD_OF*0..2]->(a:Directory)<-[:CHILD_OF*0..2]-(s:Directory)<-[:TOUCHES]-(pr:PR)<-[:APPROVED_PR]-(u:Person)
WHERE pr.merged_at < $cutoff
RETURN u.login AS login, pr.number AS pr, pr.merged_at AS at, min(length(p1)) AS hops, min(s.path) AS path"""

Q_SIG_DECIDERS = """
MATCH (d:Directory) WHERE d.path IN $cands WITH d ORDER BY size(d.path) DESC LIMIT 1
MATCH (d)-[:CHILD_OF*0..30]->(a:Directory)<-[:GOVERNS]-(o:OwnersFile)-[:LABELS]->(sg:Sig)
WITH DISTINCT sg
MATCH (sg)<-[:LABELS]-(:OwnersFile)-[:GOVERNS]->(s:Directory)<-[:TOUCHES]-(pr:PR)<-[:APPROVED_PR]-(u:Person)
WHERE pr.merged_at < $cutoff
RETURN u.login AS login, pr.number AS pr, pr.merged_at AS at, 5 AS hops, sg.id AS path"""

Q_TRAIL = """
OPTIONAL MATCH (k0:Kep) WHERE k0.number = $num
OPTIONAL MATCH (:FeatureGate {name:$name})<-[:INTRODUCES]-(k1:Kep)
WITH collect(DISTINCT k0) + collect(DISTINCT k1) AS ks UNWIND ks AS k
OPTIONAL MATCH (k)-[:INTRODUCES]->(g:FeatureGate)
OPTIONAL MATCH (k)-[:OWNED_BY]->(s:Sig)
OPTIONAL MATCH (k)<-[:APPROVED_KEP]-(a:Person)
RETURN k.number AS kep, k.title AS title, k.status AS status, k.stage AS stage, g.name AS gate, s.id AS sig, a.login AS approver"""

Q_STALE = """
MATCH (k:Kep)<-[:APPROVED_KEP]-(p:Person)
WHERE NOT k.status IN $closed
WITH k, collect(p) AS ps
WHERE none(x IN ps WHERE coalesce(x.current, false) = true)
OPTIONAL MATCH (k)-[:OWNED_BY]->(s:Sig)
RETURN k.number AS kep, k.title AS title, k.status AS status, s.id AS sig ORDER BY kep"""

Q_ROUTE = """
UNWIND $entities AS e
MATCH (o:OwnersFile)-[:LABELS]->(s:Sig)
WHERE toLower(o.path) CONTAINS toLower(e) OR toLower(s.id) CONTAINS toLower(e)
WITH s, count(DISTINCT o) AS w ORDER BY w DESC LIMIT 1
OPTIONAL MATCH (s)<-[:LABELS]-(of:OwnersFile)<-[:APPROVER_IN]-(g)
OPTIONAL MATCH (u:Person)-[:MEMBER_OF*0..3]->(g)
WITH s, u, count(DISTINCT of) AS cover WHERE u IS NOT NULL
OPTIONAL MATCH (u)-[:APPROVED_PR]->(pr:PR) WITH s, u, cover, count(pr) AS acts
ORDER BY acts DESC, cover DESC, u.login
WITH s, collect(u.login)[0..3] AS approvers
OPTIONAL MATCH (k:Kep)-[:OWNED_BY]->(s) WHERE NOT k.status IN $closed
RETURN s.id AS sig, approvers, collect(DISTINCT k.number)[0..5] AS keps"""

Q_FIND = """
MATCH (n) WHERE (n:Sig AND toLower(n.id) CONTAINS toLower($name)) OR (n:Person AND toLower(n.login) = toLower($name))
   OR (n:FeatureGate AND toLower(n.name) CONTAINS toLower($name)) OR (n:Directory AND toLower(n.path) CONTAINS toLower($name))
RETURN labels(n)[0] AS kind, coalesce(n.id, n.login, n.name, n.path) AS id LIMIT 20"""


class FalkorRepository:
    def __init__(self, graph):
        self.g = graph

    @classmethod
    def embedded(cls, db_path: str, graph: str = "org:kubernetes"):
        from redislite.falkordb_client import FalkorDB
        return cls(FalkorDB(db_path).select_graph(graph))

    @classmethod
    def remote(cls, host="localhost", port=6379, graph="org:kubernetes"):
        from falkordb import FalkorDB
        return cls(FalkorDB(host=host, port=port).select_graph(graph))

    # ---------- read path (guarded + ro_query) ----------
    def run_read(self, cypher: str, params: Optional[dict] = None) -> list:
        assert_read_only(cypher)
        res = self.g.ro_query(cypher, params or {})
        cols = [h[1] if isinstance(h, (list, tuple)) else h for h in res.header]
        return [dict(zip(cols, r)) for r in res.result_set]

    def _q(self, cypher, params, urls_from=None) -> QueryResult:
        t0 = time.perf_counter()
        rows = self.run_read(cypher, params)
        self.last_ms = (time.perf_counter() - t0) * 1000
        urls = urls_from(rows) if urls_from else []
        return QueryResult(cypher=" ".join(cypher.split()), params=params, rows=rows, urls=urls)

    @staticmethod
    def _cands(path):
        return ancestors(path if "." in path.rsplit("/", 1)[-1] else path + "/_")

    def eligible_approvers(self, path: str) -> QueryResult:
        def urls(rows):
            return sorted({f"{GH}/blob/master/{r['owners_file'] + '/' if r['owners_file'] else ''}OWNERS" for r in rows})[:5]
        return self._q(Q_ELIGIBLE, {"cands": self._cands(path)}, urls)

    def deciders(self, path: str, cutoff: Optional[datetime] = None) -> QueryResult:
        p = {"cands": self._cands(path), "cutoff": _epoch(cutoff)}
        rows = self.run_read(Q_DECIDERS, p)
        if sum(1 for r in rows if r["hops"] <= 2) < 3:  # sparse local history -> widen through the SIG label edge
            rows += self.run_read(Q_SIG_DECIDERS, p)
        out = []
        for r in rows:
            w = 1.0 / (1 + r["hops"])
            out.append({"login": r["login"], "pr": r["pr"], "at": _iso(r["at"]), "path": r["path"], "n": 1, "w": round(w, 3)})
        urls = [f"{GH}/pull/{n}" for n in sorted({r["pr"] for r in out}, reverse=True)[:5]]
        return QueryResult(" ".join((Q_DECIDERS + " ⟶ widen: " + Q_SIG_DECIDERS).split()), p, out, urls)

    def decision_trail(self, key: str) -> QueryResult:
        digits = "".join(c for c in str(key) if c.isdigit())
        num = int(digits) if digits and not any(c.isalpha() for c in str(key).replace("KEP", "").replace("-", "").replace(" ", "")) else -1
        return self._q(Q_TRAIL, {"num": num, "name": str(key)},
                       lambda rows: [f"https://github.com/kubernetes/enhancements/issues/{r['kep']}" for r in rows[:1]])

    def stale_decisions(self, sig: Optional[str] = None) -> QueryResult:
        qr = self._q(Q_STALE, {"closed": sorted(CLOSED)})
        if sig:
            qr.rows = [r for r in qr.rows if r["sig"] == sig]
        qr.urls = [f"https://github.com/kubernetes/enhancements/issues/{r['kep']}" for r in qr.rows[:3]]
        return qr

    def route_candidates(self, entities: list) -> QueryResult:
        qr = self._q(Q_ROUTE, {"entities": entities, "closed": sorted(CLOSED)})
        qr.rows = [r for r in qr.rows if r.get("sig")]
        return qr

    def find_entity(self, name: str) -> QueryResult:
        return self._q(Q_FIND, {"name": name})

    def stats(self) -> dict:
        n = self.run_read("MATCH (n) RETURN count(n) AS c")[0]["c"]
        e = self.run_read("MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
        return {"nodes": n, "edges": e}

    # ---------- write path (loader only; never reachable from the agent) ----------
    def _w(self, cypher, params=None):
        return self.g.query(cypher, params or {})

    def load_owners(self, rules: dict, aliases: dict) -> None:
        dirs = set()
        for path in rules:
            dirs.update(ancestors(path + "/_"))
        self._w("UNWIND $d AS p MERGE (:Directory {path:p})", {"d": sorted(dirs)})
        self._w("MATCH (c:Directory) WHERE c.path <> '' "
                "WITH c, CASE WHEN c.path CONTAINS '/' THEN reverse(substring(reverse(c.path), size(split(c.path,'/')[-1]) + 1)) ELSE '' END AS par "
                "MATCH (p:Directory {path: par}) MERGE (c)-[:CHILD_OF]->(p)")
        for a, members in aliases.items():
            self._w("MERGE (:Alias {name:$a})", {"a": a})
        al = [{"a": a, "m": m} for a, ms in aliases.items() for m in ms]
        for x in al:
            if x["m"] in aliases:
                self._w("MATCH (c:Alias {name:$m}), (p:Alias {name:$a}) MERGE (c)-[:MEMBER_OF]->(p)", x)
            else:
                self._w("MERGE (u:Person {login:$m}) WITH u MATCH (p:Alias {name:$a}) MERGE (u)-[:MEMBER_OF]->(p)", x)
        for path, r in rules.items():
            self._w("MERGE (o:OwnersFile {path:$p}) SET o.npo=$npo WITH o MATCH (d:Directory {path:$p}) "
                    "SET d.npo=$npo MERGE (o)-[:GOVERNS]->(d)", {"p": path, "npo": bool(r.no_parent_owners)})
            for who in r.approvers:
                if who in aliases:
                    self._w("MATCH (g:Alias {name:$w}), (o:OwnersFile {path:$p}) MERGE (g)-[:APPROVER_IN]->(o)", {"w": who, "p": path})
                else:
                    self._w("MERGE (g:Person {login:$w}) WITH g MATCH (o:OwnersFile {path:$p}) MERGE (g)-[:APPROVER_IN]->(o)", {"w": who, "p": path})
            for lab in r.labels:
                if lab.startswith("sig/"):
                    self._w("MERGE (s:Sig {id:$s}) WITH s MATCH (o:OwnersFile {path:$p}) MERGE (o)-[:LABELS]->(s)",
                            {"s": "sig-" + lab[4:], "p": path})
        self._w("MATCH (u:Person)-[:MEMBER_OF*0..3]->(g)-[:APPROVER_IN]->(:OwnersFile) SET u.current = true")

    def mark_current(self, logins) -> None:
        self._w("UNWIND $l AS x MERGE (u:Person {login:x}) SET u.current = true", {"l": sorted(logins)})

    def load_sig_leaders(self, leaders: dict) -> None:
        """leaders: sig id -> list of (login, role) with role in CHAIRS|LEADS."""
        for sid, people in leaders.items():
            self._w("MERGE (:Sig {id:$s})", {"s": sid})
            for login, role in people:
                if role not in ("CHAIRS", "LEADS"):
                    continue
                self._w(f"MERGE (u:Person {{login:$u}}) SET u.current=true WITH u MATCH (s:Sig {{id:$s}}) MERGE (u)-[:{role}]->(s)",
                        {"u": login, "s": sid})

    def upsert_prs(self, prs) -> int:
        rows = []
        for p in prs:
            dirs = sorted({d for f in p.files for d in ancestors(f)})
            leafs = sorted({"/".join(f.split("/")[:-1]) for f in p.files})
            rows.append({"n": p.number, "t": p.title[:200], "at": _epoch(p.merged_at), "au": p.author,
                         "ap": sorted(p.approvers), "dirs": dirs, "leafs": leafs, "keps": list(p.kep_refs),
                         "url": p.url or f"{GH}/pull/{p.number}"})
        B = 200
        for i in range(0, len(rows), B):
            chunk = rows[i:i + B]
            self._w("UNWIND $r AS x MERGE (pr:PR {number:x.n}) SET pr.title=x.t, pr.merged_at=x.at, pr.url=x.url "
                    "MERGE (a:Person {login:x.au}) MERGE (a)-[:AUTHORED_PR]->(pr)", {"r": chunk})
            self._w("UNWIND $r AS x UNWIND x.dirs AS d MERGE (:Directory {path:d})", {"r": chunk})
            self._w("UNWIND $r AS x UNWIND x.leafs AS d MATCH (pr:PR {number:x.n}), (dd:Directory {path:d}) MERGE (pr)-[:TOUCHES]->(dd)", {"r": chunk})
            self._w("UNWIND $r AS x UNWIND x.ap AS l MATCH (pr:PR {number:x.n}) MERGE (u:Person {login:l}) MERGE (u)-[r:APPROVED_PR]->(pr) SET r.at=x.at", {"r": chunk})
            self._w("UNWIND $r AS x UNWIND x.keps AS k MATCH (pr:PR {number:x.n}), (kk:Kep {number:k}) MERGE (pr)-[:IMPLEMENTS]->(kk)", {"r": chunk})
        return len(rows)

    def link_directory_tree(self) -> None:
        self._w("MATCH (c:Directory) WHERE c.path <> '' "
                "WITH c, CASE WHEN c.path CONTAINS '/' THEN reverse(substring(reverse(c.path), size(split(c.path,'/')[-1]) + 1)) ELSE '' END AS par "
                "MERGE (p:Directory {path: par}) MERGE (c)-[:CHILD_OF]->(p)")

    def upsert_keps(self, keps) -> int:
        for k in keps:
            self._w("MERGE (k:Kep {number:$n}) SET k.title=$t, k.status=$s, k.stage=$st", {"n": k.number, "t": k.title, "s": k.status, "st": k.stage})
            if k.owning_sig:
                self._w("MERGE (s:Sig {id:$s}) WITH s MATCH (k:Kep {number:$n}) MERGE (k)-[:OWNED_BY]->(s)", {"s": k.owning_sig, "n": k.number})
            for sg in k.participating_sigs:
                self._w("MERGE (s:Sig {id:$s}) WITH s MATCH (k:Kep {number:$n}) MERGE (k)-[:PARTICIPATES]->(s)", {"s": sg, "n": k.number})
            for g in k.feature_gates:
                self._w("MERGE (g:FeatureGate {name:$g}) WITH g MATCH (k:Kep {number:$n}) MERGE (k)-[:INTRODUCES]->(g)", {"g": g, "n": k.number})
            for a in k.approvers:
                self._w("MERGE (u:Person {login:$u}) WITH u MATCH (k:Kep {number:$n}) MERGE (u)-[:APPROVED_KEP]->(k)", {"u": a, "n": k.number})
            for a in k.authors:
                self._w("MERGE (u:Person {login:$u}) WITH u MATCH (k:Kep {number:$n}) MERGE (u)-[:AUTHORED_KEP]->(k)", {"u": a, "n": k.number})
        return len(keps)

    def kep_status(self, number: int):
        r = self.run_read("MATCH (k:Kep {number:$n}) RETURN k.status AS s", {"n": number})
        return r[0]["s"] if r else None

    def get_snapshot(self):
        r = self.run_read("MATCH (s:Snapshot) RETURN s.at AS at ORDER BY at DESC LIMIT 1")
        return datetime.fromtimestamp(r[0]["at"], tz=timezone.utc) if r else None

    def set_snapshot(self, at: datetime) -> None:
        self._w("MERGE (s:Snapshot {id:1}) SET s.at=$a", {"a": int(at.timestamp())})
