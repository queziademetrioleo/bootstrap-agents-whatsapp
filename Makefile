.DEFAULT_GOAL := help
SHELL := /bin/bash

help: ## Lista os comandos disponiveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

venv: ## Cria virtualenv com Python 3.13 e instala dependencias
	python3.13 -m venv .venv && . .venv/bin/activate && pip install -U pip && pip install -r requirements.txt

run: ## Sobe a API localmente (webhook + processador no mesmo app)
	. .venv/bin/activate && PYTHONPATH=. uvicorn agent.app:app --reload --port 8080

db-schema: ## Aplica o schema no Postgres local (usa variaveis do .env)
	psql "$$DATABASE_URL" -f scripts/init_db.sql

ingest: ## Ingere a base de conhecimento. Uso: make ingest CSV=knowledge/default.csv AGENT=default
	. .venv/bin/activate && PYTHONPATH=. python scripts/ingest.py --csv $(CSV) --agent-id $(AGENT)

lint: ## Roda o ruff
	. .venv/bin/activate && ruff check .

fmt: ## Formata com ruff
	. .venv/bin/activate && ruff format .

tf-plan: ## terraform plan (workspace dev). Uso: make tf-plan ENV=dev
	cd infra/terraform && terraform workspace select $(or $(ENV),dev) && terraform plan -var-file=$(or $(ENV),dev).tfvars

tf-apply: ## terraform apply. Uso: make tf-apply ENV=dev
	cd infra/terraform && terraform workspace select $(or $(ENV),dev) && terraform apply -var-file=$(or $(ENV),dev).tfvars

.PHONY: help venv run db-schema ingest lint fmt tf-plan tf-apply
