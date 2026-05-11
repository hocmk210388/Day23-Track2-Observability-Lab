## Day 23 Track 2 — Observability Lab orchestration
##
## Quick start:
##   make setup    # one-time: pull images, create .env
##   make up       # start the 7-service stack
##   make smoke    # verify all services healthy
##   make demo     # run end-to-end demo (load + alert + trace + drift)
##   make verify   # rubric gate — exit 0 if all checkpoints pass
##   make down     # stop the stack
##   make clean    # stop + remove volumes (destructive)

SHELL := /bin/bash
COMPOSE ?= docker compose

# Prefer active conda/venv so drift/load use the same deps as `pip install -r requirements.txt`.
# Override: `make PYTHON=/path/to/python drift`
PYTHON ?= $(shell \
	if [ -n "$$CONDA_PREFIX" ] && [ -f "$$CONDA_PREFIX/python.exe" ]; then printf '%s' "$$CONDA_PREFIX/python.exe"; \
	elif [ -n "$$CONDA_PREFIX" ] && [ -f "$$CONDA_PREFIX/bin/python" ]; then printf '%s' "$$CONDA_PREFIX/bin/python"; \
	elif [ -n "$$VIRTUAL_ENV" ] && [ -f "$$VIRTUAL_ENV/Scripts/python.exe" ]; then printf '%s' "$$VIRTUAL_ENV/Scripts/python.exe"; \
	elif [ -n "$$VIRTUAL_ENV" ] && [ -f "$$VIRTUAL_ENV/bin/python" ]; then printf '%s' "$$VIRTUAL_ENV/bin/python"; \
	elif command -v python >/dev/null 2>&1; then command -v python; \
	elif command -v python3 >/dev/null 2>&1; then command -v python3; \
	else printf '%s' python3; fi)

.PHONY: help setup up down restart logs smoke load alert trace drift demo verify clean lint-dashboards sync-slack-url

help:
	@grep -E '^##|^[a-zA-Z_-]+:.*?## ' Makefile | sed -E 's/^## ?//; s/:.*## /\t/' | column -t -s $$'\t'

setup: ## one-time install + .env scaffold
	@test -f .env || cp .env.example .env
	@bash 00-setup/pull-images.sh
	@$(PYTHON) 00-setup/verify-docker.py
	@$(MAKE) sync-slack-url

sync-slack-url: ## write alertmanager/slack_url from .env (required before compose up)
	@$(PYTHON) scripts/sync-alertmanager-slack-url.py

up: sync-slack-url ## start the stack
	$(COMPOSE) up -d
	@echo "Stack starting. Run 'make smoke' to verify (allow ~30s for first start)."

down: ## stop the stack (preserves volumes)
	$(COMPOSE) down

restart: down up ## stop + start

logs: ## tail logs from all services
	$(COMPOSE) logs -f --tail=50

smoke: ## health-check all 7 services
	@echo "Checking services..."
	@curl -fsS http://localhost:8000/healthz   > /dev/null && echo "  app:           OK"
	@curl -fsS http://localhost:9090/-/healthy > /dev/null && echo "  prometheus:    OK"
	@curl -fsS http://localhost:9093/-/healthy > /dev/null && echo "  alertmanager:  OK"
	@curl -fsS http://localhost:3000/api/health | grep -qE '"database"[[:space:]]*:[[:space:]]*"ok"' && echo "  grafana:       OK"
	@i=1; while [ $$i -le 30 ]; do \
	  if curl -fsS http://localhost:3100/ready >/dev/null 2>&1; then echo "  loki:          OK"; break; fi; \
	  if [ $$i -eq 30 ]; then echo "  loki:          FAIL (still 503 after ~60s — check: docker logs day23-loki)" >&2; exit 1; fi; \
	  sleep 2; \
	  i=$$((i+1)); \
	done
	@curl -fsS http://localhost:16686/         > /dev/null && echo "  jaeger:        OK"
	@curl -fsS http://localhost:8888/metrics   > /dev/null && echo "  otel-collector: OK"
	@echo "Stack healthy."

load: ## run baseline locust load (concurrency=10, 60s)
	cd 02-prometheus-grafana/load-test && \
	  $(PYTHON) -m locust -f locustfile.py --headless -u 10 -r 2 -t 60s --host http://localhost:8000

alert: ## trigger an alert by killing the app, wait, then restore
	bash scripts/trigger-alert.sh

trace: ## generate one traced request and print its trace_id
	@curl -sS -X POST http://localhost:8000/predict \
	  -H 'Content-Type: application/json' \
	  -d '{"prompt":"hello"}' | $(PYTHON) -c 'import json,sys; d=json.load(sys.stdin); print("trace_id:",d.get("trace_id","?"))'

drift: ## run drift detection notebook (cli mode)
	cd 04-drift-detection && $(PYTHON) scripts/drift_detect.py

demo: ## end-to-end demo (load -> alert -> trace -> drift)
	$(MAKE) load
	$(MAKE) alert
	$(MAKE) trace
	$(MAKE) drift

verify: ## rubric gate — exits 0 only if all checkpoints pass
	$(PYTHON) scripts/verify.py

lint-dashboards: ## validate Grafana dashboard JSONs
	$(PYTHON) scripts/lint-dashboards.py 02-prometheus-grafana/grafana/dashboards/*.json

clean: ## stop stack + remove volumes (DESTRUCTIVE)
	$(COMPOSE) down -v
