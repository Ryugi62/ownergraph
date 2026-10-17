"""`ownergraph load|ask|eval-e1|serve|mcp`"""
from __future__ import annotations
import argparse, json, os
from datetime import datetime, timezone
from pathlib import Path

RAW = Path("data/raw")
CUTOFF = datetime(2026, 8, 1, tzinfo=timezone.utc)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ownergraph")
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("load")
    l.add_argument("--profile", choices=["demo", "e1"], default="demo")
    a = sub.add_parser("ask")
    a.add_argument("question")
    e = sub.add_parser("eval-e1")
    e.add_argument("--limit", type=int)
    e.add_argument("--out", default="results/e1.json")
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--host", default=os.environ.get("OWNERGRAPH_HOST", "127.0.0.1"))
    sub.add_parser("mcp")
    args = ap.parse_args(argv)
    if args.cmd == "load":
        from .composition import make_repo
        from .loader import load_profile
        print(json.dumps(load_profile(make_repo(), RAW, args.profile, CUTOFF)))
    elif args.cmd == "ask":
        from .composition import build_services
        from ..application.serialize import answer_to_dict
        service, _, _ = build_services()
        print(json.dumps(answer_to_dict(service.ask(args.question)), indent=2, default=str))
    elif args.cmd == "eval-e1":
        from .e1_run import run
        r = run(RAW, "data/e1.db", Path(args.out), args.limit)
        print(json.dumps({k: r[k] for k in ("n_eval", "segment_sizes", "methods")}, indent=1))
    elif args.cmd == "serve":
        import uvicorn
        from .composition import build_services
        from ..adapters.http_api import create_app
        service, _, _ = build_services()
        uvicorn.run(create_app(service), host=args.host, port=args.port)
    elif args.cmd == "mcp":
        from ..adapters.mcp_server import main as mcp_main
        mcp_main()


if __name__ == "__main__":
    main()
