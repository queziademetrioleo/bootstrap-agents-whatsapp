# Guia do Código — como configurar e estender o agente

Este guia é o ponto de partida para qualquer pessoa que vá **configurar um agente,
criar tools, integrar APIs externas ou atualizar a base de FAQ**. Ele dá o
panorama e aponta para os guias detalhados de cada tópico.

A ideia central do template: você **não precisa entender o core** para criar ou
estender um agente. Tudo que você mexe está em quatro pastas — `tools/`,
`integrations/`, `knowledge/` e `config/` — e em um registro no banco
(`agent_configs`). O resto (`agent/`) é infraestrutura imutável.

---

## 1. Filosofia: o que é core e o que é seu

| Pasta | É core? | Você mexe? |
|-------|---------|------------|
| `agent/` | ✅ core imutável | ❌ não (sem decisão do time) |
| `tools/` | ❌ | ✅ uma tool por arquivo |
| `integrations/` | ❌ | ✅ um cliente de API por arquivo |
| `knowledge/` | ❌ | ✅ CSVs de FAQ por agente |
| `config/` | ❌ | ✅ variáveis por ambiente |
| `scripts/` | parcial | ✅ você roda (`ingest.py`, `create_agent.py`) |
| `infra/` | infra | só quem faz deploy |

O `agent/` faz o trabalho pesado (receber a mensagem, RAG, chamar o Gemini,
executar tools, responder). Você nunca precisa abrir esses arquivos para colocar
um agente novo no ar.

---

## 2. Mapa do repositório

```
agent/            core imutável (não mexa)
├── app.py            API FastAPI: /webhook (recebe) e /pubsub/push (processa)
├── core.py           o loop do agente (orquestra tudo)
├── rag.py            busca na base de conhecimento
├── tool_base.py      o contrato de uma tool (AgentTool)
├── tool_registry.py  auto-discovery das tools
├── followup.py       cadência de re-engajamento
├── guardrails.py     Model Armor (anti prompt-injection)
├── memory.py         usuários, histórico, idempotência, config de agente
├── redis_client.py   sessão curta de conversa
├── evolution.py      envio de mensagem / "digitando..."
└── ...

tools/            👈 SUA ZONA — uma tool por arquivo
integrations/     👈 SUA ZONA — clientes de APIs externas
knowledge/        👈 SUA ZONA — CSVs de FAQ (Pergunta,Resposta) por agente
config/           👈 SUA ZONA — dev.env / prod.env
scripts/          ingest.py (RAG), create_agent.py, init_db.sql
infra/            Terraform, Dockerfile, Cloud Build (deploy)
docs/             os guias (você está lendo um)
```

---

## 3. Anatomia de um agente

Um "agente" (um cliente/projeto) é definido por **um registro na tabela
`agent_configs`** mais a base de conhecimento dele. Não é preciso novo
repositório nem novo serviço — tudo roda no mesmo Cloud Run, roteado pelo
`instance_name` que chega no webhook.

Campos de `agent_configs`:

| Campo | O que é |
|-------|---------|
| `instance_name` | nome da instância da Evolution (= o número de WhatsApp). Chega no webhook e identifica o agente. |
| `agent_id` | isola a base de conhecimento (`knowledge_base.agent_id`). |
| `system_prompt` | a persona/instruções do agente. |
| `tools_enabled` | lista de tools de domínio/integração ativas (as universais entram sozinhas). |
| `config` | JSONB para configurações extras (ex.: `followup`). |

Você **não edita o banco na mão** — usa o script:

```bash
python scripts/create_agent.py \
  --instance loja-acme \
  --agent-id acme \
  --system-prompt "Voce e a atendente da Loja Acme..." \
  --tools check_order_status
```

Roteiro completo de um agente novo: **[creating-a-new-agent.md](creating-a-new-agent.md)**.

---

## 4. Tools — dar capacidades ao agente

Uma tool é uma função que o Gemini pode chamar durante a conversa (consultar
estoque, status de pedido, calcular preço...). Você cria **um arquivo** em
`tools/` e o sistema descobre sozinho — sem editar config central.

Esqueleto:

```python
# tools/consultar_estoque.py
from agent.tool_base import AgentTool, ToolContext

async def _run(ctx: ToolContext, produto: str) -> dict:
    return {"produto": produto, "disponivel": True, "qtd": 12}

TOOL = AgentTool(
    name="consultar_estoque",
    description="Consulta o estoque de um produto pelo nome.",  # o Gemini lê isto
    parameters={
        "type": "object",
        "properties": {"produto": {"type": "string", "description": "Nome do produto"}},
        "required": ["produto"],
    },
    handler=_run,
    category="domain",   # universal | domain | integration
)
```

Categorias: **universal** (entra em todo agente), **domain** (precisa estar em
`tools_enabled`), **integration** (usa uma API externa). Detalhes, regras e o
aviso de segurança (não confiar nos argumentos do modelo): **[adding-a-tool.md](adding-a-tool.md)**.

---

## 5. Integrações com APIs externas

Quando uma tool precisa falar com um sistema de terceiro (CRM, ERP, Google
Calendar...), o código do cliente HTTP fica em `integrations/` — separado da tool.
O `HttpClient` base (`integrations/base.py`) já traz timeout, retry e leitura de
segredos.

```python
# integrations/meu_crm.py
from integrations.base import HttpClient, secret

def _client():
    return HttpClient("https://api.crm.com", default_headers={
        "Authorization": f"Bearer {secret('MEU_CRM_TOKEN')}"
    })

async def buscar_cliente(ctx, documento: str) -> dict | None:
    resp = await _client().get(f"/clientes/{documento}")
    return resp.json() if resp.status_code == 200 else None
```

Credenciais **nunca** ficam no código — vão para o **Secret Manager** e são lidas
por `secret("NOME")`. Como declarar o segredo e usar a integração numa tool:
**[adding-an-integration.md](adding-an-integration.md)**.

---

## 6. Base de conhecimento (FAQ / RAG)

A base é um **CSV** com duas colunas: `Pergunta` e `Resposta`. Você edita o CSV;
o sistema cuida de embeddings e busca. A cada mensagem, o agente busca os pares
mais parecidos e injeta no contexto automaticamente (não precisa tool).

```csv
Pergunta,Resposta
Quais os horarios de atendimento?,"Funcionamos de seg a sex, 8h-18h, e sabados 9h-13h."
Como rastreio meu pedido?,"Me informe o numero do pedido que eu consulto."
```

Depois de editar, rode a ingestão (um CSV por agente, via `agent_id`):

```bash
python scripts/ingest.py --csv knowledge/acme.csv --agent-id acme
```

Como funciona o threshold (0.75), o top-k e a sincronização sem downtime:
**[updating-knowledge-base.md](updating-knowledge-base.md)**.

---

## 7. Features de UX (configuráveis por agente)

| Feature | O que faz | Onde liga |
|---------|-----------|-----------|
| **Debounce** | agrupa várias bolhas ("oi" / "tudo bem?" / "tenho dúvida") numa única resposta | env `DEBOUNCE_SECONDS` (0 desliga) → [message-debouncing.md](message-debouncing.md) |
| **"Digitando..."** | mostra o status enquanto o agente gera a resposta | env `TYPING_INDICATOR` |
| **Follow-up** | re-engaja quem sumiu, em stages (`fixed` = msg fixa, `summary` = gerada do histórico) | por agente em `agent_configs.config.followup` → [follow-ups.md](follow-ups.md) |
| **Guardrails** | Model Armor filtra prompt injection, jailbreak, conteúdo perigoso | env `MODEL_ARMOR_ENABLED` |
| **Echo (dev)** | em local, loga a resposta em vez de enviar à Evolution | env `EVOLUTION_ECHO=true` |

---

## 8. O que acontece quando chega uma mensagem (fluxo)

Para entender o sistema sem ler o core, a sequência do `agent/core.py`:

1. **Idempotência** — descarta a mensagem se já foi processada.
2. **Contexto** — carrega o perfil do usuário e o histórico curto (Redis).
3. **Guardrail de entrada** — Model Armor checa a mensagem (se ligado).
4. **RAG** — busca na base de conhecimento do `agent_id` e injeta o que achar.
5. **Gemini + tools** — chama o modelo; se ele pedir uma tool, executa e devolve;
   repete até a resposta final.
6. **Guardrail de saída** — checa a resposta gerada (se ligado).
7. **Persiste** — grava o turno no Redis (curto) e Postgres (longo).
8. **Responde** — envia pela Evolution; reinicia a cadência de follow-up.

O webhook receiver só **recebe e enfileira** (Pub/Sub); quem roda esse fluxo é o
processador. Os dois são o mesmo código (`agent/app.py`), em serviços separados.

---

## 9. Variáveis de ambiente e segredos

A referência completa é o **[`.env.example`](../.env.example)**. As principais:

| Variável | Para que |
|----------|----------|
| `GEMINI_MODEL` | modelo na Vertex AI (**`gemini-2.5-flash`**) |
| `GCP_PROJECT_ID` / `GCP_LOCATION` | projeto e região |
| `DB_*` / `REDIS_*` | conexão com Postgres e Redis |
| `RAG_SCORE_THRESHOLD` / `RAG_TOP_K` | sensibilidade do RAG |
| `DEBOUNCE_SECONDS` / `TYPING_INDICATOR` | UX de conversa |
| `MODEL_ARMOR_ENABLED` | guardrails |
| `WEBHOOK_TOKEN` / `EVOLUTION_API_KEY` | autenticação com a Evolution |
| `EVOLUTION_ECHO` | modo dev (loga em vez de enviar) |

Regra de segredos: **credenciais do GCP** (Vertex, Cloud SQL, Redis, Model Armor)
são por **IAM** (sem chave no código). **Credenciais de terceiros** (CRM, ERP)
ficam no **Secret Manager**.

---

## 10. Atalhos

- **Criar um agente novo (cliente):** [creating-a-new-agent.md](creating-a-new-agent.md)
- **Rodar o projeto na sua máquina:** [local-development.md](local-development.md)
- **Subir tudo no GCP:** [deploy-gcp.md](deploy-gcp.md)
- **Adicionar tool:** [adding-a-tool.md](adding-a-tool.md)
- **Adicionar integração:** [adding-an-integration.md](adding-an-integration.md)
- **Atualizar a base de FAQ:** [updating-knowledge-base.md](updating-knowledge-base.md)
