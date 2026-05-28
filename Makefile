.PHONY: help install env build up up-api down ensure-db test-db drop-test-db migrate create_migration test run celery health setup logs

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
FLASK := $(VENV)/bin/flask
PYTEST := $(VENV)/bin/pytest
CELERY := $(VENV)/bin/celery
BACKEND := backend

export FLASK_APP := run:app

.DEFAULT_GOAL := help

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Create virtualenv and install Python dependencies
	@test -d $(VENV) || python3 -m venv $(VENV)
	$(PIP) install -r $(BACKEND)/requirements.txt

env: ## Copy backend/.env.example to backend/.env if missing
	@test -f $(BACKEND)/.env || cp $(BACKEND)/.env.example $(BACKEND)/.env

build: env ## Build the API Docker image
	docker compose build api

up: ## Start PostgreSQL and Redis (docker compose)
	docker compose up -d postgres redis
	@$(MAKE) ensure-db
	@$(MAKE) test-db

ensure-db: ## Create application database if it does not exist
	@cd $(BACKEND) && ../$(PYTHON) -c "from dotenv import load_dotenv; load_dotenv(); from app.migrations.create_db import ensure_postgres_database_from_env; ensure_postgres_database_from_env()"

up-api: build ## Start PostgreSQL, Redis, and the Flask API container
	docker compose up -d
	@$(MAKE) test-db

down: ## Stop all Docker Compose services
	docker compose down

test-db: ## Create test database if it does not exist
	@docker compose exec postgres psql -U postgres -tc \
		"SELECT 1 FROM pg_database WHERE datname = 'business_creator_test'" | grep -q 1 \
		|| docker compose exec postgres psql -U postgres -c "CREATE DATABASE business_creator_test;"

drop-test-db: ## Drop PostgreSQL test database (business_creator_test)
	@cd $(BACKEND) && ../$(PYTHON) -c "from dotenv import load_dotenv; load_dotenv(); from app.migrations.create_db import drop_test_database_from_env; drop_test_database_from_env()"

migrate: ## Apply pending Pony migrations
	cd $(BACKEND) && MIGRATE_MODE=1 ../$(PYTHON) -m app.migrations.commands.run

create_migration: ## Create migration stub (usage: make create_migration name=add_users)
	@test -n "$(name)" || (echo 'Usage: make create_migration name=describe_your_change' && exit 1)
	cd $(BACKEND) && ../$(PYTHON) -m app.migrations.commands.create_migration "$(name)"

test: install ## Run the test suite (in-memory SQLite; drops Postgres test DB if present)
	@ec=0; (cd $(BACKEND) && ../$(PYTEST)) || ec=$$?; \
	$(MAKE) drop-test-db; exit $$ec

run: install env up ## Run the Flask API server (applies pending migrations on startup)
	cd $(BACKEND) && FLASK_ENV=development ../$(PYTHON) run.py

celery: install env up ## Run the Celery worker
	cd $(BACKEND) && ../$(CELERY) -A celery_worker.celery worker --loglevel=info

health: ## Check API health (local `make run` or `make up-api`)
	@curl -sf http://127.0.0.1:5000/health | python3 -m json.tool

logs: ## Follow docker compose logs
	docker compose logs -f

setup: install env up test-db migrate ## Bootstrap local development
	@echo "Setup complete. Run 'make run' to start the API."
