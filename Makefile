.PHONY: help install env up down test-db migrate migrate-create test run celery health setup logs

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

up: ## Start PostgreSQL and Redis (docker compose)
	docker compose up -d
	@$(MAKE) test-db

down: ## Stop PostgreSQL and Redis
	docker compose down

test-db: ## Create test database if it does not exist
	@docker compose exec postgres psql -U postgres -tc \
		"SELECT 1 FROM pg_database WHERE datname = 'business_creator_test'" | grep -q 1 \
		|| docker compose exec postgres psql -U postgres -c "CREATE DATABASE business_creator_test;"

migrate: ## Apply database migrations
	cd $(BACKEND) && ../$(FLASK) db upgrade

migrate-create: ## Create a new migration (usage: make migrate-create MSG="your message")
	@test -n "$(MSG)" || (echo 'Usage: make migrate-create MSG="describe your change"' && exit 1)
	cd $(BACKEND) && ../$(FLASK) db migrate -m "$(MSG)"

test: install up ## Run the test suite
	cd $(BACKEND) && ../$(PYTEST)

run: install env up migrate ## Run the Flask API server
	cd $(BACKEND) && ../$(PYTHON) run.py

celery: install env up ## Run the Celery worker
	cd $(BACKEND) && ../$(CELERY) -A celery_worker.celery worker --loglevel=info

health: ## Check API health (server must be running)
	@curl -sf http://127.0.0.1:5000/health | python3 -m json.tool

logs: ## Follow docker compose logs
	docker compose logs -f

setup: install env up test-db migrate ## Bootstrap local development
	@echo "Setup complete. Run 'make run' to start the API."
