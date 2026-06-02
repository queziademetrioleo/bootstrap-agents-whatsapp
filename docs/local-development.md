# Rodar o projeto localmente

Guia passo a passo. **Siga na ordem** — cada passo depende do anterior. Depois de
cada passo tem um ✅ **Confira** para você ter certeza de que deu certo antes de
seguir. Se algo falhar, pule para a [tabela de erros](#erros-comuns) no fim.

---

## Pré-requisitos (instale tudo antes de começar)

### 1. Python 3.13 (NÃO use 3.14)

O `pydantic-core` compila uma extensão Rust que **ainda não suporta o Python
3.14**. Use exatamente o 3.13.

- **Mac:** `brew install python@3.13`
- **Linux (Ubuntu 24.04+):** `sudo apt install python3.13 python3.13-venv`
- **Linux (outras):** `sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.13 python3.13-venv`
- **Windows:** baixe em [python.org/3.13](https://www.python.org/downloads/release/python-3130/)

✅ **Confira:** `python3.13 --version` → deve mostrar `Python 3.13.x`

> Se você usa **Conda**, ele pode forçar outra versão. Crie um ambiente isolado:
> `conda create -n agent python=3.13 -y && conda activate agent`. Mesmo com
> `(base)` aparecendo no prompt, o que importa é o `.venv` (passo 2) estar ativo.

### 2. Docker (instalado E rodando)

- **Mac / Windows:** instale o **Docker Desktop** e **abra o app** — ele precisa
  estar rodando antes de qualquer comando `docker`.
- **Linux:** Docker Engine. Verifique: `sudo systemctl status docker` (inicie com
  `sudo systemctl start docker`). Para não precisar de `sudo`:
  `sudo usermod -aG docker $USER` (requer logout/login).

✅ **Confira:** `docker ps` → deve listar uma tabela (mesmo vazia), sem erro de
"Cannot connect to the Docker daemon".

### 3. gcloud autenticado (para a Vertex AI)

Embeddings e LLM usam a Vertex AI mesmo em local. Autentique com Application
Default Credentials:

```bash
gcloud auth application-default login
```

✅ **Confira:** o comando abre o navegador e termina com "Credentials saved".

---

## Passo 1 — Clonar o repositório

```bash
git clone https://github.com/queziademetrioleo/bootstrap-agents-whatsapp.git
cd bootstrap-agents-whatsapp
```

✅ **Confira:** `pwd` termina em `/bootstrap-agents-whatsapp`. **Todos os comandos
abaixo são rodados a partir daqui** (a raiz do repo). Se um comando falhar com
"No such file or directory", quase sempre é porque você não está nesta pasta.

---

## Passo 2 — Criar o ambiente Python e instalar dependências

```bash
make venv
```

Isso cria o `.venv` com Python 3.13, ativa e instala tudo — **em sequência, numa
tacada só**. Depois, **ative o venv** na sua sessão de terminal:

```bash
. .venv/bin/activate
```

✅ **Confira:**

```bash
which python                          # deve apontar para .../.venv/bin/python
python -c "import asyncpg; print('ok')"   # deve imprimir: ok
```

> ⚠️ **Não rode os passos separados.** Se você criar o venv e depois rodar
> `pip install` sem ter ativado o `.venv`, o install vai para o Python errado (ex.:
> o Conda `base`) e os módulos não serão encontrados. Em caso de dúvida, refaça:
> `rm -rf .venv && make venv`.
>
> **Sem `make` (Windows)?**
> ```bash
> python3.13 -m venv .venv
> .venv\Scripts\activate
> pip install -U pip
> pip install -r requirements.txt
> ```

---

## Passo 3 — Configurar o `.env`

```bash
cp .env.example .env
```

Abra o `.env` e ajuste para o ambiente local (Postgres/Redis em Docker):

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
MODEL_ARMOR_ENABLED=false          # guardrails off em local (sem template)
```

✅ **Confira:** `cat .env | grep USE_CLOUD_SQL` → mostra `USE_CLOUD_SQL=false`.

---

## Passo 4 — Subir o banco e ingerir a base (UM comando)

Este comando faz **tudo na ordem certa**: remove containers antigos, sobe Postgres
(com o usuário `agent` já criado) e Redis, **espera o Postgres ficar pronto**,
aplica o schema e ingere a base de conhecimento de exemplo:

```bash
make dev-up
```

✅ **Confira:** termina com `✅ Pronto!`. Verifique os containers:

```bash
docker ps    # agent-pg e agent-redis devem aparecer como "Up"
```

> **Por que um comando só?** Os erros mais comuns (container já existe, usuário
> `agent` não existe, "connection refused" porque o Postgres ainda não subiu,
> rodar o ingest antes do schema) acontecem quando se faz isso na mão fora de
> ordem. O `make dev-up` elimina todos eles.
>
> **Para zerar tudo e recomeçar:** `make dev-down && make dev-up`.

<details>
<summary>Quer fazer manualmente (entender o que acontece)?</summary>

```bash
# 1. remove containers antigos para evitar conflito de nome
docker rm -f agent-pg agent-redis 2>/dev/null || true

# 2. sobe Postgres (o POSTGRES_USER cria o usuario/banco 'agent') e Redis
docker run -d --name agent-pg -p 5432:5432 \
  -e POSTGRES_USER=agent -e POSTGRES_PASSWORD=agent -e POSTGRES_DB=agent \
  pgvector/pgvector:pg15
docker run -d --name agent-redis -p 6379:6379 redis:7

# 3. ESPERE o Postgres aceitar conexoes (senao o proximo passo falha)
until docker exec agent-pg pg_isready -U agent >/dev/null 2>&1; do sleep 1; done

# 4. aplica o schema usando o psql DE DENTRO do container (nao precisa psql local)
docker exec -i agent-pg psql -U agent -d agent < scripts/init_db.sql

# 5. ingere a base de conhecimento
PYTHONPATH=. python scripts/ingest.py --csv knowledge/default.csv --agent-id default
```
</details>

---

## Passo 5 — Rodar a API

```bash
make run     # uvicorn em http://127.0.0.1:8080
```

✅ **Confira:** em outro terminal:

```bash
curl localhost:8080/healthz    # deve responder {"status":"ok"}
```

---

## Passo 6 — Simular uma mensagem (sem Evolution/Pub/Sub)

Com a API rodando, teste o processador montando o envelope do Pub/Sub:

```bash
PAYLOAD=$(printf '{"message_id":"m1","instance_name":"default","phone":"5511999999999","name":"Teste","text":"Quais os horarios de atendimento?"}' | base64)
curl -s -X POST localhost:8080/pubsub/push \
  -H 'Content-Type: application/json' \
  -d "{\"message\":{\"data\":\"$PAYLOAD\"}}"
```

✅ **Confira:** nos logs do `make run` aparece `RAG retrieve` e `Turno concluido`.

> O envio final via Evolution (`evolution.send_text`) vai falhar em local (você
> não tem uma Evolution rodando) — **isso é esperado**. O resto do fluxo (RAG,
> Gemini, persistência) roda normalmente.

---

## Erros comuns

Mapeamento direto **erro → causa → solução** (os erros que de fato aparecem):

| Mensagem de erro | Causa | Solução |
|---|---|---|
| `cp: .env.example: No such file or directory` | Você não está na raiz do repo | `cd bootstrap-agents-whatsapp` (passo 1) |
| `the configured Python interpreter version (3.14) is newer than PyO3's maximum` | Python 3.14 | Use 3.13: `rm -rf .venv && python3.13 -m venv .venv && ...` |
| `ModuleNotFoundError: No module named 'agent'` | Faltou `PYTHONPATH=.` | Use os comandos `make` (já incluem) ou prefixe `PYTHONPATH=.` |
| `ModuleNotFoundError: No module named 'asyncpg'` | `pip install` foi pro Python errado | Ative o `.venv` e reinstale: `rm -rf .venv && make venv` |
| `Conflict. The container name "/agent-pg" is already in use` | Container antigo existe | `make dev-down` (ou `docker rm -f agent-pg agent-redis`) e tente de novo |
| `role "agent" does not exist` | Container criado sem as variáveis, OU schema não aplicado | `make dev-down && make dev-up` (recria do zero, na ordem) |
| `connection to server at "127.0.0.1", port 5432 failed: Connection refused` | Postgres ainda não subiu / não está rodando | `docker start agent-pg` e espere; ou `make dev-up` (já espera ficar pronto) |
| `psql: command not found` | `psql` não instalado | Não precisa — use `make db-schema` (roda via `docker exec`) |
| `Cannot connect to the Docker daemon` | Docker não está rodando | Abra o Docker Desktop (Mac/Win) ou `sudo systemctl start docker` (Linux) |

---

## Resetar tudo e começar do zero

Se quiser limpar e refazer:

```bash
make dev-down        # remove os containers
rm -rf .venv         # remove o ambiente Python
make venv            # recria o ambiente
. .venv/bin/activate
make dev-up          # banco + schema + base, na ordem
make run             # sobe a API
```

## Notas

- Não commite o `.env` (já está no `.gitignore`).
- Para testar o webhook receiver de ponta a ponta, suba a Evolution localmente
  (`docker compose`) e aponte o webhook dela para
  `http://host.docker.internal:8080/webhook` com o header `x-webhook-token`.
