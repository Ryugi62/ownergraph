"""AC-18 / condition #7: README numbers are generated from results JSON; a mismatch fails."""
import re

SHOWN = ("all", "hard", "no_nearby_history", "eligible_all_inactive")
START, END = "<!-- numbers:start -->", "<!-- numbers:end -->"


class ReadmeMismatch(Exception):
    pass


def render_numbers_block(results: dict) -> str:
    e1 = results.get("e1", {})
    lines = [f"- E1 evaluated PRs (merged after cutoff, with a non-author approver): {e1.get('n_eval', 'n/a')}"]
    for name, segs in e1.get("methods", {}).items():
        for seg, m in segs.items():
            if seg not in SHOWN:
                continue
            lines.append(f"- E1 {name} [{seg}] hit@3: {m['hit@3'] * 100:.1f}%" + (f" (hit@1 {m['hit@1'] * 100:.1f}%, n={m['n']})" if "hit@1" in m else ""))
    for seg, d in e1.get("paired_graph_minus_owners_history_hit3", {}).items():
        if seg in SHOWN:
            lines.append(f"- E1 graph minus owners_history [{seg}] hit@3: {d['diff'] * 100:+.1f} pp "
                         f"(95% CI {d['ci95'][0] * 100:+.1f} to {d['ci95'][1] * 100:+.1f}, n={d['n']})")
    e2 = results.get("e2")
    if e2:
        n = e2["n"]
        for name, acc in e2["systems"].items():
            lines.append(f"- E2 {name} [single-hop, n={n['single']}] accuracy: {acc['single'] * 100:.1f}%")
            lines.append(f"- E2 {name} [multi-hop, n={n['multi']}] accuracy: {acc['multi'] * 100:.1f}%")
        if "ablation_multi_drop_pp" in e2:
            lines.append(f"- E2 ablation (graph tools removed -> vector RAG), multi-hop drop: {e2['ablation_multi_drop_pp']:.1f} pp")
    t = results.get("tests")
    if t:
        lines.append(f"- Tests: {t['passed']}/{t['total']} passing")
    for k, v in results.get("extra", {}).items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def check_readme(readme: str, results: dict) -> None:
    m = re.search(re.escape(START) + r"\n(.*?)\n" + re.escape(END), readme, re.S)
    if not m:
        raise ReadmeMismatch("numbers block markers missing")
    if m.group(1).strip() != render_numbers_block(results).strip():
        raise ReadmeMismatch("README numbers differ from results JSON")


def write_readme_block(readme: str, results: dict) -> str:
    block = f"{START}\n{render_numbers_block(results)}\n{END}"
    if START in readme:
        return re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: block, readme, flags=re.S)
    return readme + "\n" + block + "\n"
