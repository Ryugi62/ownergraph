PY ?= .venv/bin/python

setup:
	uv venv --python 3.12 .venv && uv pip install falkordblite falkordb pytest pyyaml fastapi uvicorn httpx "mcp<2"

data:            ## download public inputs (OWNERS, sigs.yaml, kep.yaml, merged PRs); needs gh auth
	$(PY) scripts/fetch_data.py

load:            ## build the demo graph (embedded FalkorDB, ~20 s)
	$(PY) -m ownergraph load --profile demo

test:
	$(PY) -m pytest -q

eval:            ## regenerate every number in the README: tests, E1, E2 (E2 needs GEMINI_API_KEY), README block
	$(PY) scripts/record_tests.py
	$(PY) -m ownergraph eval-e1
	$(PY) -m ownergraph eval-e2
	$(PY) -m ownergraph readme-numbers

readme-numbers:
	$(PY) -m ownergraph readme-numbers

demo:            ## UI + API on http://127.0.0.1:8000
	$(PY) -m ownergraph serve --port 8000

.PHONY: setup data load test eval readme-numbers demo
