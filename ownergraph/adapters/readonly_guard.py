"""Read-only guard (AC-15): 'the model got to suggest and a read-only query got to decide'.
Rejects any write keyword outside string literals, multi-statement input, and CALL outside an allow-list."""
import re


class WriteQueryRejected(ValueError):
    pass


WRITE = {"CREATE", "MERGE", "DELETE", "DETACH", "SET", "REMOVE", "DROP", "FOREACH", "LOAD"}
CALL_ALLOW = ("db.labels", "db.relationshiptypes", "db.propertykeys", "algo.pagerank", "algo.bfs", "algo.sppaths", "algo.spPaths".lower())
_STR = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"")


def assert_read_only(cypher: str) -> None:
    bare = _STR.sub("''", re.sub(r"//[^\n]*|/\*.*?\*/", " ", cypher, flags=re.S))
    if ";" in bare.strip().rstrip(";"):
        raise WriteQueryRejected("multiple statements")
    for tok in re.findall(r"[A-Za-z_][A-Za-z_0-9.]*", bare):
        if tok.upper() in WRITE:
            raise WriteQueryRejected(f"write keyword {tok.upper()} is not allowed on the read path")
    for m in re.finditer(r"\bCALL\s+([A-Za-z_][\w.]*)", bare, re.I):
        if m.group(1).lower() not in CALL_ALLOW:
            raise WriteQueryRejected(f"procedure {m.group(1)} is not on the allow-list")
