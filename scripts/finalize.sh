#!/bin/sh
# after eval-e2 wrote results/e2.json: record tests, refresh README numbers, check, commit
set -e
.venv/bin/python scripts/record_tests.py
.venv/bin/python -m ownergraph readme-numbers
.venv/bin/python -m ownergraph readme-numbers --check
git add -A
git -c user.name=Ryugi62 -c user.email=xorjf1027@gmail.com commit -qm "Record E2 results and regenerate README numbers"
