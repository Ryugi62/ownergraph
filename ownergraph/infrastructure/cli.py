"""`ownergraph load|ask|eval-e1|serve|mcp`"""
from __future__ import annotations
import argparse, json, os
from datetime import datetime, timezone
from pathlib import Path

RAW = Path(os.environ.get("OWNERGRAPH_DATA", "data/snapshot"))
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
    e2 = sub.add_parser("eval-e2")
    e2.add_argument("--out", default="results/e2.json")
    e2.add_argument("--interval", type=float, default=4.5)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--host", default=os.environ.get("OWNERGRAPH_HOST", "127.0.0.1"))
    s.add_argument("--load-if-empty", action="store_true", help="build the demo graph first when the database has none")
    sub.add_parser("mcp")
    rd = sub.add_parser("readme-numbers")
    rd.add_argument("--check", action="store_true")
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
    elif args.cmd == "eval-e2":
        from .e2_run import run as run_e2_
        r = run_e2_(RAW, Path("data/e2/questions.json"), "data/ownergraph.db", Path(args.out), args.interval)
        print(json.dumps({k: r[k] for k in ("n", "systems", "by_type") if k in r}, indent=1))
    elif args.cmd == "serve":
        import uvicorn
        from .composition import build_services
        from ..adapters.http_api import create_app
        service, repo, _ = build_services()
        if args.load_if_empty and repo.stats()["nodes"] == 0:
            from .loader import load_profile
            print("empty graph: loading snapshot", load_profile(repo, RAW, "demo", CUTOFF), flush=True)
        uvicorn.run(create_app(service, repo), host=args.host, port=args.port)
    elif args.cmd == "readme-numbers":
        from .readme_numbers import check_readme, write_readme_block
        res = {}
        for key in ("e1", "e2", "tests"):
            f = Path("results") / f"{key}.json"
            if f.exists():
                res[key] = json.loads(f.read_text())
        readme = Path("README.md").read_text(encoding="utf-8")
        if args.check:
            check_readme(readme, res)
            print("README numbers match results/*.json")
        else:
            Path("README.md").write_text(write_readme_block(readme, res), encoding="utf-8")
            print("README numbers block rewritten from results/*.json")
    elif args.cmd == "mcp":
        from ..adapters.mcp_server import main as mcp_main
        mcp_main()


if __name__ == "__main__":
    main()
