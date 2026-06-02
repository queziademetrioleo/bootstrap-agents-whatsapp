# Desenvolvimento local

Este guia descreve como executar o projeto em uma máquina local, do zero até a
aplicação no ar. Os passos são sequenciais: cada um depende da conclusão do
anterior. Ao final de cada etapa há uma verificação para confirmar o sucesso
antes de prosseguir. Em caso de falha, consulte a seção
[Solução de problemas](#solução-de-problemas).

## Requisitos

| Ferramenta | Versão | Observação |
|------------|--------|------------|
| Python | 3.11 – 3.13 | O `pydantic-core` depende do PyO3, que ainda não é compatível com a versão 3.14 ou superior. Recomenda-se a 3.13. |
| Docker | Engine ou Desktop | Necessário e em execução para o Postgres e o Redis locais. |
| Google Cloud SDK | atual | Autenticado via Application Default Credentials (embeddings e LLM usam a Vertex AI mesmo em ambiente local). |

### Instalação do Python 3.13

| Sistema | Comando |
|---------|---------|
| macOS | `brew install python@3.13` |
| Ubuntu 24.04+ | `sudo apt install python3.13 python3.13-venv` |
| Outras distribuições Linux | `sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.13 python3.13-venv` |
| Windows | Instalador oficial em [python.org](https://www.python.org/downloads/release/python-3130/) |

**Verificação:** `python3.13 --version` deve retornar `Python 3.13.x`.

> Usuários de Conda: para evitar conflito de versão, crie um ambiente dedicado com
> `conda create -n agent python=3.13 -y && conda activate agent`. O ambiente
> virtual criado no passo 2 (`.venv`) tem precedência sobre o Conda.

### Docker

- **macOS e Windows:** instale o Docker Desktop e mantenha o aplicativo aberto.
- **Linux:** instale o Docker Engine. Verifique o serviço com
  `sudo systemctl status docker` e inicie-o, se necessário, com
  `sudo systemctl start docker`. Para dispensar o `sudo`, adicione o usuário ao
  grupo `docker`: `sudo usermod -aG docker $USER` (requer novo login).

**Verificação:** `docker ps` deve exibir a tabela de containers sem erros de
conexão com o daemon.

### Autenticação na Google Cloud

```bash
gcloud auth application-default login
```

**Verificação:** o fluxo abre o navegador e finaliza com a mensagem de credenciais
salvas.

## Passo 1 — Clonar o repositório

```bash
git clone https://github.com/queziademetrioleo/bootstrap-agents-whatsapp.git
cd bootstrap-agents-whatsapp
```

Todos os comandos seguintes assumem que o diretório atual é a raiz do
repositório.

**Verificação:** `pwd` termina em `/bootstrap-agents-whatsapp`.

## Passo 2 — Ambiente Python e dependências

```bash
make venv
source .venv/bin/activate
```

O comando `make venv` cria o ambiente virtual com Python 3.13, ativa-o e instala
as dependências em uma única operação.

**Verificação:**

```bash
which python                            # deve apontar para .venv/bin/python
python -c "import asyncpg; print('ok')" # deve imprimir: ok
```

> Execute a instalação por meio do `make venv`. Ativar o ambiente e rodar
> `pip install` em etapas separadas pode direcionar a instalação ao interpretador
> incorreto (por exemplo, o ambiente Conda base). Em caso de inconsistência,
> recrie o ambiente: `rm -rf .venv && make venv`.

No Windows, sem o `make`:

```powershell
python3.13 -m venv .venv
.venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt
```

## Passo 3 — Variáveis de ambiente

```bash
cp .env.example .env
```

Edite o arquivo `.env` com os valores do ambiente local:

```
USE_CLOUD_SQL=false
DB_HOST=127.0.0.1
DB_PORT=5433
DB_USER=agent
DB_PASSWORD=agent
DB_NAME=agent
REDIS_HOST=127.0.0.1
REDIS_PORT=6380
GCP_PROJECT_ID=seu-projeto-gcp
GCP_LOCATION=southamerica-east1
MODEL_ARMOR_ENABLED=false
```

As portas 5433 (Postgres) e 6380 (Redis) são usadas no host para evitar conflito
com instâncias nativas que costumam ocupar as portas padrão 5432 e 6379.

**Verificação:** `grep USE_CLOUD_SQL .env` retorna `USE_CLOUD_SQL=false`.

## Passo 4 — Banco de dados e base de conhecimento

```bash
make dev-up
```

Este comando executa todas as etapas de infraestrutura na ordem correta: remove
containers anteriores, inicia o Postgres (com o usuário `agent` provisionado) e o
Redis, aguarda o banco aceitar conexões, aplica o schema e ingere a base de
conhecimento de exemplo.

**Verificação:** a execução termina com a mensagem de conclusão. Confirme os
containers em execução:

```bash
docker ps   # agent-pg e agent-redis devem constar com status "Up"
```

Para reiniciar a infraestrutura local do zero, utilize `make dev-down` seguido de
`make dev-up`.

A execução manual equivalente, caso prefira acompanhar cada etapa:

```bash
docker rm -f agent-pg agent-redis 2>/dev/null || true

docker run -d --name agent-pg -p 5433:5432 \
  -e POSTGRES_USER=agent -e POSTGRES_PASSWORD=agent -e POSTGRES_DB=agent \
  pgvector/pgvector:pg15
docker run -d --name agent-redis -p 6380:6379 redis:7

until docker exec agent-pg pg_isready -U agent >/dev/null 2>&1; do sleep 1; done

docker exec -i agent-pg psql -U agent -d agent < scripts/init_db.sql
PYTHONPATH=. python scripts/ingest.py --csv knowledge/default.csv --agent-id default
```

## Passo 5 — Executar a aplicação

```bash
make run
```

A API sobe em `http://127.0.0.1:8080`.

**Verificação:** em outro terminal, `curl localhost:8080/healthz` retorna
`{"status":"ok"}`.

## Passo 6 — Testar o fluxo de processamento

Com a API em execução, simule uma mensagem montando o envelope do Pub/Sub:

```bash
PAYLOAD=$(printf '{"message_id":"m1","instance_name":"default","phone":"5511999999999","name":"Teste","text":"Quais os horarios de atendimento?"}' | base64)
curl -s -X POST localhost:8080/pubsub/push \
  -H 'Content-Type: application/json' \
  -d "{\"message\":{\"data\":\"$PAYLOAD\"}}"
```

**Verificação:** os logs da aplicação registram as entradas `RAG retrieve` e
`Turno concluido`.

O envio final pela Evolution API falha em ambiente local, pois não há uma
instância da Evolution em execução. Esse comportamento é esperado; as demais
etapas (RAG, geração via Gemini e persistência) são concluídas normalmente.

## Solução de problemas

| Mensagem de erro | Causa | Solução |
|------------------|-------|---------|
| `cp: .env.example: No such file or directory` | Diretório de trabalho incorreto | Execute `cd bootstrap-agents-whatsapp` (passo 1). |
| `the configured Python interpreter version (3.14) is newer than PyO3's maximum` | Python 3.14 ou superior | Utilize a versão 3.13: `rm -rf .venv && make venv`. |
| `ModuleNotFoundError: No module named 'agent'` | `PYTHONPATH` não definido | Use os comandos `make`, que já o definem, ou prefixe com `PYTHONPATH=.`. |
| `ModuleNotFoundError: No module named 'asyncpg'` | Dependências instaladas no interpretador incorreto | Recrie o ambiente: `rm -rf .venv && make venv`. |
| `Conflict. The container name "/agent-pg" is already in use` | Container anterior existente | `make dev-down` e tente novamente. |
| `role "agent" does not exist` (no ingest, mas o schema aplicou) | Há um Postgres nativo ocupando a porta do host, interceptando a conexão | As portas locais são 5433/6380 justamente para evitar isso; confirme `DB_PORT=5433` e `REDIS_PORT=6380` no `.env` e rode `make dev-down && make dev-up`. |
| `role "agent" does not exist` (schema não aplicou) | Container criado sem as variáveis de ambiente | `make dev-down && make dev-up`. |
| `connection ... port 5432 failed: Connection refused` | Postgres ainda não disponível | `make dev-up` aguarda a disponibilidade automaticamente. |
| `psql: command not found` | Cliente `psql` ausente | Não é necessário: `make db-schema` executa via `docker exec`. |
| `Cannot connect to the Docker daemon` | Docker não está em execução | Inicie o Docker Desktop ou `sudo systemctl start docker`. |

## Comandos disponíveis

| Comando | Descrição |
|---------|-----------|
| `make venv` | Cria o ambiente virtual e instala as dependências. |
| `make dev-up` | Provisiona Postgres e Redis, aplica o schema e ingere a base. |
| `make dev-down` | Remove os containers locais. |
| `make run` | Executa a API localmente. |
| `make ingest CSV=… AGENT=…` | Ingere uma base de conhecimento. |
| `make db-schema` | Aplica apenas o schema (via `docker exec`). |

## Reinicializar o ambiente

```bash
make dev-down
rm -rf .venv
make venv
source .venv/bin/activate
make dev-up
make run
```

## Observações

- O arquivo `.env` não deve ser versionado; já consta no `.gitignore`.
- Para testar o webhook de ponta a ponta, execute a Evolution API localmente e
  configure o webhook para `http://host.docker.internal:8080/webhook`, incluindo o
  cabeçalho `x-webhook-token`.
