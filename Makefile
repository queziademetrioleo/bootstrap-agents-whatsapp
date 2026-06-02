.DEFAULT_GOAL := help
SHELL := /bin/bash

help: ## Lista os comandos disponiveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

venv: ## Cria virtualenv com Python 3.13 e instala dependencias
	python3.13 -m venv .venv && . .venv/bin/activate && pip install -U pip && pip install -r requirements.txt

run: ## Sobe a API localmente (webhook + processador no mesmo app)
	. .venv/bin/activate && PYTHONPATH=. uvicorn agent.app:app --reload --port 8080

dev-up: ## Sobe Postgres+Redis, espera ficar pronto, aplica schema e ingere a base (tudo de uma vez)
	@echo "🧹  Removendo containers antigos (se existirem)..."
	@docker rm -f agent-pg agent-redis >/dev/null 2>&1 || true
	@echo "🐘  Subindo Postgres (pgvector) e Redis..."
	docker run -d --name agent-pg -p 5432:5432 \
	  -e POSTGRES_USER=agent -e POSTGRES_PASSWORD=agent -e POSTGRES_DB=agent \
	  pgvector/pgvector:pg15
	docker run -d --name agent-redis -p 6379:6379 redis:7
	@echo "⏳  Aguardando o Postgres aceitar conexoes..."
	@until docker exec agent-pg pg_isready -U agent >/dev/null 2>&1; do sleep 1; done
	@echo "📐  Aplicando o schema..."
	docker exec -i agent-pg psql -U agent -d agent < scripts/init_db.sql
	@echo "📚  Ingerindo a base de conhecimento de exemplo..."
	. .venv/bin/activate && PYTHONPATH=. python scripts/ingest.py --csv knowledge/default.csv --agent-id default
	@echo "✅  Pronto! Banco e base prontos. Rode 'make run' para subir a API."

dev-down: ## Para e remove os containers locais (Postgres + Redis)
	docker rm -f agent-pg agent-redis >/dev/null 2>&1 || true
	@echo "🛑  Containers removidos."

db-schema: ## Aplica so o schema no Postgres local (via docker exec — nao precisa de psql instalado)
	docker exec -i agent-pg psql -U agent -d agent < scripts/init_db.sql

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

.PHONY: help venv run dev-up dev-down db-schema ingest lint fmt tf-plan tf-apply
