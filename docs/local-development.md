# Rodar o projeto localmente

## Pré-requisitos

- Python 3.11+
- Docker Desktop instalado e **aberto/rodando** (no Mac: abra o app Docker Desktop
  antes de rodar qualquer `docker` no terminal — sem ele os comandos falham)
- `gcloud` autenticado com ADC: `gcloud auth application-default login`
  (necessário porque embeddings e LLM usam Vertex AI mesmo em local)

## 1. Clonar o repositório

```bash
git clone https://github.com/queziademetrioleo/bootstrap-agents-whatsapp.git
cd bootstrap-agents-whatsapp
```

> Todos os comandos a seguir assumem que você está na raiz do repositório.

## 2. Subir Postgres (com pgvector) e Redis locais

```bash
docker run -d --name agent-pg -p 5432:5432 \
  -e POSTGRES_USER=agent \
  -e POSTGRES_PASSWORD=agent \
  -e POSTGRES_DB=agent \
  pgvector/pgvector:pg15

docker run -d --name agent-redis -p 6379:6379 redis:7
```

## 3. Configurar o ambiente

```bash
cp .env.example .env
```

Edite o `.env` para apontar ao Postgres/Redis locais:

```
USE_CLOUD_SQL=false
DB_HOST=127.0.0.1
DB_PORT=5432
DB_USER=agent
DB_PASSWORD=agent
DB_NAME=agent
REDIS_HOST=127.0.0.1
GCP_PROJECT_ID=seu-projeto-gcp     # precisa de Vertex AI habilitado
GCP_LOCATION=southamerica-east1
```

## 4. Instalar dependências

```bash
make venv
```

## 5. Criar o schema

```bash
. .venv/bin/activate
psql "postgresql://agent:agent@127.0.0.1:5432/agent" -f scripts/init_db.sql
```

## 6. Ingerir a base de conhecimento de exemplo

```bash
make ingest CSV=knowledge/default.csv AGENT=default
```

## 7. Rodar a API

```bash
make run     # uvicorn em http://127.0.0.1:8080
```

Health check: `curl localhost:8080/healthz`

## 8. Simular uma mensagem (sem Evolution/Pub/Sub)

Você pode testar o processador direto, montando o envelope do Pub/Sub:

```bash
PAYLOAD=$(printf '{"message_id":"m1","instance_name":"default","phone":"5511999999999","name":"Teste","text":"Quais os horarios de atendimento?"}' | base64)
curl -s -X POST localhost:8080/pubsub/push \
  -H 'Content-Type: application/json' \
  -d "{\"message\":{\"data\":\"$PAYLOAD\"}}"
```

> Em local, o envio final via Evolution (`evolution.send_text`) vai falhar se você
> não tiver uma Evolution rodando — o resto do fluxo (RAG, Gemini, persistência)
> roda normalmente. Veja os logs estruturados no stdout.

## Notas

- Não commite o `.env` (já está no `.gitignore`).
- Para testar o webhook receiver de ponta a ponta, suba a Evolution localmente
  (`docker compose`) e aponte `WEBHOOK_GLOBAL_URL` para `http://host.docker.internal:8080/webhook`.
