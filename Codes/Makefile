# WASL — one-command demo:  cp .env.example .env && make demo
COMPOSE ?= docker compose
EXEC    ?= $(COMPOSE) exec -T backend
PY      ?= backend/.venv/bin/python

.PHONY: up down migrate seed train demo test test-backend test-frontend lint reset-demo logs local-setup

up:            ## build and start db + backend + frontend
	$(COMPOSE) up -d --build
	@echo "Waiting for the API…"; for i in $$(seq 1 60); do curl -sf localhost:8000/api/health >/dev/null && break; sleep 2; done
	@curl -s localhost:8000/api/health; echo

down:
	$(COMPOSE) down

migrate:
	$(EXEC) alembic upgrade head

seed:
	$(EXEC) python -m app.synth.seed

train:         ## train risk + uplift models, register, score open loops, write docs/MODEL_CARD.md
	$(EXEC) python -m app.ml.train --seed 42

demo: up migrate seed train   ## reset + seed + train + score + start
	@echo "WASL is running → http://localhost:5173  (jury login: DevTest / DevTest11)"

reset-demo:
	$(EXEC) python -c "from app.db import session_scope; from app.api.demo import reset_everything; s=session_scope().__enter__(); print(reset_everything(s)['counts']); s.commit()"

test: test-backend test-frontend

test-backend:  ## pytest against Postgres (TEST_DATABASE_URL) or SQLite fallback
	cd backend && .venv/bin/python -m pytest --cov=app --cov-report=term-missing:skip-covered

test-frontend:
	cd frontend && npm test

lint:
	cd backend && .venv/bin/ruff check app tests && (.venv/bin/mypy app || true)
	cd frontend && npx tsc -b

logs:
	$(COMPOSE) logs -f backend

local-setup:   ## without Docker: python venv + node modules
	python3.11 -m venv backend/.venv && backend/.venv/bin/pip install -e "backend[dev]"
	cd frontend && npm install
