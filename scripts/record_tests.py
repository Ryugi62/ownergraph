"""Runs the suite and records passed/total into results/tests.json (README numbers come from it)."""
import json, re, subprocess, sys
out = subprocess.run([sys.executable, "-m", "pytest", "-q"], capture_output=True, text=True)
m = re.search(r"(\d+) passed", out.stdout)
failed = re.search(r"(\d+) failed", out.stdout)
passed, nfail = int(m.group(1)) if m else 0, int(failed.group(1)) if failed else 0
json.dump({"passed": passed, "total": passed + nfail}, open("results/tests.json", "w"))
print(out.stdout.strip().splitlines()[-1])
sys.exit(out.returncode)
