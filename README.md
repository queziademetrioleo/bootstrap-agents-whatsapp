# WhatsApp AI Agent Bootstrap

Template **open de uso interno** para criar agentes de IA no WhatsApp, gerenciados
inteiramente no GCP.

**Modelo: 1 repositório = 1 cliente = 1 deploy isolado.** Para cada cliente novo,
você clona este repositório, configura a persona/tools/base e faz o deploy num
projeto GCP próprio (Cloud Run próprio, Evolution própria, banco próprio).
Isolamento total: dados, billing e blast radius separados por cliente.

> Cliente médico → `git clone` → deploy. Suporte de vendas de drones → outro
> `git clone` → outro deploy. E assim por diante.

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
         embeddings)       RAG)
```

O **webhook receiver** só valida + publica no Pub/Sub e responde 200. O
**processador** roda o loop do agente: idempotência → contexto → RAG automático →
Gemini com function calling → persistência → resposta. Detalhes em `agent/core.py`.

**UX de conversa:** mensagens quebradas em várias bolhas são agrupadas numa única
resposta (debounce — ver [docs/message-debouncing.md](docs/message-debouncing.md))
e o agente mostra **"digitando..."** enquanto gera a resposta (`TYPING_INDICATOR`,
via `POST /chat/sendPresence` da Evolution; lógica em `agent/evolution.py:typing`).

## Estrutura

```
agent/          core imutável (loop, memória, RAG, tools, app FastAPI)
tools/          zona do colaborador — uma tool por arquivo (auto-discovery)
integrations/   clientes de APIs externas — uma por arquivo
knowledge/      CSVs da base de conhecimento (Pergunta,Resposta)
config/         agent.yaml (persona/tools/follow-up) + dev.env/prod.env
scripts/        ingest.py (RAG), init_db.sql
infra/          Terraform, Dockerfile, cloudbuild.yaml
docs/           guias passo a passo
```

> A pasta `agent/` é o **core imutável** — não altere sem decisão do time. Tudo que
> um colaborador precisa está em `tools/`, `integrations/`, `knowledge/` e `config/`.

## Começando

**Comece por aqui — dois guias completos:**

- 📘 **[Guia do Código](docs/guia-do-codigo.md)** — onde fica o quê, como criar
  tools, integrações e a base de FAQ. Para quem vai configurar/estender o agente.
- 🚀 **[Guia de Deploy GCP](docs/deploy-gcp.md)** — passo a passo sequencial para
  subir tudo no GCP via CLI/Terraform.

Guias detalhados por tópico:

- **Rodar local:** [docs/local-development.md](docs/local-development.md)
- **Configurar o agente deste cliente:** [docs/creating-a-new-agent.md](docs/creating-a-new-agent.md)
- **Adicionar uma tool:** [docs/adding-a-tool.md](docs/adding-a-tool.md)
- **Adicionar uma integração:** [docs/adding-an-integration.md](docs/adding-an-integration.md)
- **Atualizar a base de conhecimento (RAG):** [docs/updating-knowledge-base.md](docs/updating-knowledge-base.md)
- **Agrupar mensagens em bolhas (debounce):** [docs/message-debouncing.md](docs/message-debouncing.md)
- **Follow-up / re-engajamento:** [docs/follow-ups.md](docs/follow-ups.md)

## Um repositório por cliente

Cada cliente é um **deploy isolado**: você clona o repositório, define a persona,
as tools e a base de conhecimento **dele**, e sobe num **projeto GCP próprio**.

- **Persona / tools / follow-up:** um único arquivo, [`config/agent.yaml`](config/agent.yaml).
- **Base de conhecimento:** o(s) CSV(s) em `knowledge/` (ingeridos com `ingest.py`).
- **Infra:** Cloud Run, Cloud SQL, Memorystore e Evolution próprios desse cliente.

Nada é compartilhado entre clientes — cada `git clone` é uma instalação completa e
independente. Para um cliente novo, repita o processo num projeto GCP novo.

## Nota sobre o modelo

O sistema usa **`gemini-2.5-flash`** (via Vertex AI) em todo o pipeline — geração e
function calling. O ID é configurável pela variável `GEMINI_MODEL` (env do Cloud Run,
controlada pela variável Terraform `gemini_model`); para trocar de modelo, basta
alterar esse valor — nada no código fica chumbado no nome.
