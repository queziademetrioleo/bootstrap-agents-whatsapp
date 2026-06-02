# WhatsApp AI Agent Bootstrap

Template **open de uso interno** para criar agentes de IA no WhatsApp, gerenciados
inteiramente no GCP. Clone, configure e deploye. Cada agente novo (cliente/projeto)
roda no mesmo serviço, com sua própria persona, tools e base de conhecimento.

## Stack

| Camada | Tecnologia |
|---|---|
| LLM | Gemini via **Vertex AI** (SDK `google-genai`, sem API key) |
| Embeddings | `text-embedding-004` (768 dims) via Vertex AI |
| WhatsApp | Evolution API (self-hosted em Compute Engine e2-micro) |
| Memória curta | Redis (Memorystore) |
| Banco + RAG | PostgreSQL + PgVector (Cloud SQL) |
| Runtime | Cloud Run (webhook receiver + processador) |
| Fila | Pub/Sub |
| Segredos externos | Secret Manager (só APIs de terceiros) |
| CI/CD | Cloud Build + Artifact Registry |
| IaC | Terraform |

## Arquitetura

```
WhatsApp ──> Evolution API (Compute Engine)
                  │ webhook HTTP (HMAC)
                  ▼
        Cloud Run: webhook receiver ──> Pub/Sub ──push──> Cloud Run: processador
                                                                  │
              ┌───────────────────────────────────────────────────┤
              ▼                  ▼                 ▼                ▼
        Vertex AI         Cloud SQL+PgVector   Memorystore     Evolution API
        (Gemini +         (users, conversas,   (sessão curta)  (envia resposta)
         embeddings)       RAG, configs)
```

O **webhook receiver** só valida + publica no Pub/Sub e responde 200. O
**processador** roda o loop do agente: idempotência → contexto → RAG automático →
Gemini com function calling → persistência → resposta. Detalhes em `agent/core.py`.

## Estrutura

```
agent/          core imutável (loop, memória, RAG, tools, app FastAPI)
tools/          zona do colaborador — uma tool por arquivo (auto-discovery)
integrations/   clientes de APIs externas — uma por arquivo
knowledge/      CSVs da base de conhecimento (Pergunta,Resposta) por agente
scripts/        ingest.py (RAG), create_agent.py, init_db.sql
config/         configs por ambiente (dev/prod)
infra/          Terraform, Dockerfile, cloudbuild.yaml
docs/           guias passo a passo
```

> A pasta `agent/` é o **core imutável** — não altere sem decisão do time. Tudo que
> um colaborador precisa está em `tools/`, `integrations/`, `knowledge/` e `config/`.

## Começando

- **Rodar local:** [docs/local-development.md](docs/local-development.md)
- **Adicionar uma tool:** [docs/adding-a-tool.md](docs/adding-a-tool.md)
- **Adicionar uma integração:** [docs/adding-an-integration.md](docs/adding-an-integration.md)
- **Atualizar a base de conhecimento (RAG):** [docs/updating-knowledge-base.md](docs/updating-knowledge-base.md)
- **Criar um novo agente (cliente):** [docs/creating-a-new-agent.md](docs/creating-a-new-agent.md)
- **Agrupar mensagens em bolhas (debounce):** [docs/message-debouncing.md](docs/message-debouncing.md)
- **Deploy no GCP:** [docs/deploying.md](docs/deploying.md)

## Multitenancy

Cada cliente = um agente = uma instância Evolution (número) + um registro em
`agent_configs` (system prompt, tools ativas) + uma base própria em `knowledge_base`
filtrada por `agent_id`. Tudo no mesmo Cloud Run, roteado pelo `instance_name` que
chega no webhook. Sem novo repositório, sem novo serviço.

## Nota sobre o modelo

O ID do modelo (`GEMINI_MODEL`) é configurável via env. O valor padrão segue o plano
(`gemini-3.5-flash`). Se a Vertex AI retornar `NOT_FOUND` para esse ID na sua região,
troque para um ID válido (ex.: `gemini-2.5-flash`) — só essa linha, nada no código
está chumbado no nome do modelo.
