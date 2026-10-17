"""AC-18 / condition #7: README numbers are generated from results JSON; a mismatch fails."""
import re

START, END = "<!-- numbers:start -->", "<!-- numbers:end -->"


class ReadmeMismatch(Exception):
    pass


def render_numbers_block(results: dict) -> str:
    e1 = results.get("e1", {})
    lines = [f"- E1 evaluated PRs (merged after cutoff, with a non-author approver): {e1.get('n_eval', 'n/a')}"]
    for name, segs in e1.get("methods", {}).items():
        for seg, m in segs.items():
            lines.append(f"- E1 {name} [{seg}] hit@3: {m['hit@3'] * 100:.1f}%" + (f" (hit@1 {m['hit@1'] * 100:.1f}%, n={m['n']})" if "hit@1" in m else ""))
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
