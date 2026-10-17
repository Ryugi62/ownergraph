"""Data directory access: a file may be stored plain or gzipped (data/snapshot ships gzipped)."""
from __future__ import annotations
import gzip
from pathlib import Path


def read_text(d: Path, name: str) -> str:
    p = Path(d) / name
    if p.exists():
        return p.read_text(encoding="utf-8")
    return gzip.open(Path(d) / (name + ".gz"), "rt", encoding="utf-8").read()


def write_gz(d: Path, name: str, text: str) -> None:
    with gzip.open(Path(d) / (name + ".gz"), "wt", encoding="utf-8") as f:
        f.write(text)
