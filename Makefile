# Startup pipeline for harness_ai. Run `make` (or `make help`) to list targets.

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
STAMP := $(VENV)/.installed

.DEFAULT_GOAL := help
.PHONY: help setup install-all run serve web-setup web up test clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

$(PY):  ## (internal) create the virtualenv
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

# Reinstall the base deps only when requirements.txt changes (order-only venv dep).
$(STAMP): requirements.txt | $(PY)
	$(PIP) install -r requirements.txt
	touch $(STAMP)

setup: $(STAMP)  ## Create the venv and install the base dependency (Anthropic + dotenv)

install-all: setup  ## Also install optional backends (OpenAI, Google) and the HTTP API
	$(PIP) install openai google-genai fastapi uvicorn

run: setup  ## Run one task: make run TASK="..." [ORCHESTRATE=1] [TEST_CMD="pytest -q"]
	$(PY) main.py $(if $(ORCHESTRATE),--orchestrate,) $(if $(TEST_CMD),--test-command "$(TEST_CMD)",) "$(TASK)"

serve: setup  ## Serve the control-panel API on http://127.0.0.1:8000
	$(PIP) install fastapi uvicorn
	$(PY) -m harness.api

web/node_modules: web/package.json
	cd web && npm install

web-setup: web/node_modules  ## Install the web panel dependencies (npm)

web: web-setup  ## Run the web control panel (Next.js dev server on :3000)
	cd web && npm run dev

up: setup web-setup  ## Run the WHOLE system: API (:8000) + web panel (:3000) together
	@$(PIP) install fastapi uvicorn >/dev/null
	@echo "API   -> http://127.0.0.1:8000"
	@echo "Panel -> http://localhost:3000   (Ctrl+C stops both)"
	@trap 'kill 0' INT TERM EXIT; \
	$(PY) -m harness.api & \
	( cd web && npm run dev ) & \
	wait

test: setup  ## Run the test suite
	$(PY) -m unittest discover -s tests

clean:  ## Remove the venv, caches, run artifacts and web build/deps
	rm -rf $(VENV) harness_runs .pytest_cache web/node_modules web/.next
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
