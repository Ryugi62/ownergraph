"""GitHub adapter: public data only (OWNERS, sigs.yaml, kep.yaml, merged PRs). Uses the `gh` CLI token for the GraphQL API
(5,000 points/h) and raw.githubusercontent.com for file bodies."""
from __future__ import annotations
import json, subprocess, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

PR_QUERY = """
query($q:String!, $after:String){ rateLimit{cost remaining}
 search(query:$q, type:ISSUE, first:30, after:$after){ issueCount pageInfo{hasNextPage endCursor}
  nodes{... on PullRequest{ number title url bodyText author{login} mergedAt
    labels(first:20){nodes{name}} files(first:100){nodes{path}}
    comments(first:60){nodes{author{login} body createdAt}} }}}}"""


def gh_graphql(query: str, **variables) -> dict:
    args = ["gh", "api", "graphql", "-f", f"query={query}"]
    for k, v in variables.items():
        if v is not None:
            args += ["-f", f"{k}={v}"]
    out = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(out.stderr[:300])
    return json.loads(out.stdout)


def gh_rest(path: str):
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(out.stderr[:300])
    return json.loads(out.stdout)


def raw(repo: str, ref: str, path: str) -> str | None:
    url = f"https://raw.githubusercontent.com/{repo}/{ref}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


def fetch_merged_prs(repo: str, start: date, end: date, out: Path, step_days: int = 1, log=print) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if out.exists():
        seen = {json.loads(l)["number"] for l in out.open()}
    n = 0
    d0 = start
    with out.open("a") as f:
        while d0 <= end:
            d1 = min(d0 + timedelta(days=step_days - 1), end)
            after = None
            while True:
                j = gh_graphql(PR_QUERY, q=f"repo:{repo} is:pr is:merged merged:{d0}..{d1}", after=after)["data"]
                for node in j["search"]["nodes"]:
                    if node and node["number"] not in seen:
                        seen.add(node["number"]); f.write(json.dumps(node) + "\n"); n += 1
                if not j["search"]["pageInfo"]["hasNextPage"]:
                    break
                after = j["search"]["pageInfo"]["endCursor"]
            log(f"{d0}..{d1} total={n} remaining={j['rateLimit']['remaining']}")
            d0 = d1 + timedelta(days=1)
    return n


def commit_before(repo: str, iso: str) -> str:
    return gh_rest(f"repos/{repo}/commits?until={iso}&per_page=1")[0]["sha"]


def owners_paths(repo: str, sha: str) -> list[str]:
    tree = gh_rest(f"repos/{repo}/git/trees/{sha}?recursive=1")
    return [t["path"] for t in tree["tree"] if t["type"] == "blob" and (t["path"] == "OWNERS" or t["path"].endswith("/OWNERS"))]


def fetch_files(repo: str, ref: str, paths: list[str], workers: int = 16) -> dict[str, str]:
    with ThreadPoolExecutor(workers) as ex:
        bodies = list(ex.map(lambda p: raw(repo, ref, p), paths))
    return {p: b for p, b in zip(paths, bodies) if b is not None}


def kep_paths(sha: str = "master") -> list[str]:
    tree = gh_rest(f"repos/kubernetes/enhancements/git/trees/{sha}?recursive=1")
    return [t["path"] for t in tree["tree"] if t["path"].startswith("keps/") and t["path"].endswith("/kep.yaml")]
