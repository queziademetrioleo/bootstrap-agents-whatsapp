# Como adicionar uma tool

Uma tool é uma função que o Gemini pode chamar durante a conversa (function
calling). Você cria **um arquivo** em `tools/` e pronto — o sistema descobre e
registra a tool automaticamente (auto-discovery). Você **não edita** nenhum
arquivo de configuração central.

## Anatomia de uma tool

Cada arquivo em `tools/` expõe uma variável de módulo chamada `TOOL`:

```python
# tools/consultar_clima.py
from agent.tool_base import AgentTool, ToolContext

async def _run(ctx: ToolContext, cidade: str) -> dict:
    # ctx te dá: ctx.user, ctx.agent_id, ctx.instance_name, ctx.config
    # Retorne SEMPRE algo serializável em JSON (idealmente um dict).
    return {"cidade": cidade, "clima": "ensolarado", "temp_c": 28}

TOOL = AgentTool(
    name="consultar_clima",                    # snake_case, único
    description=(                              # o Gemini lê isto para decidir quando usar
        "Consulta o clima atual de uma cidade brasileira. "
        "Use quando o usuário perguntar sobre tempo/temperatura."
    ),
    parameters={                              # JSON Schema dos argumentos
        "type": "object",
        "properties": {
            "cidade": {"type": "string", "description": "Nome da cidade"},
        },
        "required": ["cidade"],
    },
    handler=_run,
    category="domain",                        # "universal" | "domain" | "integration"
)
```

## Regras do contrato

- O handler **precisa ser `async def`** e receber `ctx: ToolContext` como 1º argumento.
- `name`: snake_case alfanumérico, único entre todas as tools.
- `description`: escreva em linguagem natural e seja específico sobre *quando* usar —
  é isso que o modelo lê para decidir.
- `parameters`: JSON Schema do tipo `object`. Os nomes das `properties` viram os
  kwargs do handler.
- Retorne um `dict` (ou algo serializável). Em erro, levante exceção — o core captura
  e devolve `{"error": ...}` ao modelo, sem derrubar a conversa.

## Categorias

| Categoria | Quando usar | Ativação |
|---|---|---|
| `universal` | vale para todo agente (ex.: salvar nota) | sempre ativa |
| `domain` | específica de um cliente/projeto | precisa estar em `tools_enabled` do agente |
| `integration` | usa uma API externa (importa de `integrations/`) | igual a domain |

## Ativar uma tool de domínio

Tools `universal` já entram automaticamente. Tools `domain`/`integration` precisam
ser listadas em `tools_enabled` no [`config/agent.yaml`](../config/agent.yaml):

```yaml
tools_enabled:
  - consultar_clima
  - check_order_status
```

O nome corresponde ao campo `name` do `AgentTool`. Reinicie o `make run` (local)
ou faça um novo deploy (produção) para a mudança valer.

## ⚠️ Segurança — não confie nos argumentos do modelo

Os argumentos da tool são decididos pelo **modelo**, que pode ser manipulado pela
mensagem do usuário (prompt injection). Portanto:

- A **identidade confiável é `ctx.user`** (autenticada pelo número de WhatsApp),
  **não** o que o modelo passa. Nunca aceite um `user_id`/`telefone`/`cpf` vindo
  como argumento da tool para decidir de quem é o dado — use `ctx.user`.
- Em operações **sensíveis** (pagamento, troca de cadastro, exclusão), valide
  regras de negócio na tool e considere exigir confirmação explícita.
- O **Model Armor** (guardrails) já filtra prompt injection/jailbreak na entrada,
  mas é defesa em profundidade — a tool ainda deve ser segura por si.
- Faça `quote()` em valores do modelo usados em path de URL (ver
  `integrations/example_crm.py`).

## Testando

Rode o app local (`make run`) e dispare uma mensagem que acione a tool (veja
`docs/local-development.md`). Os logs mostram `Tool executada` com o nome.

## Exemplos no repositório

- `tools/save_user_note.py` — universal
- `tools/search_conversation_history.py` — universal
- `tools/example_check_order_status.py` — domain, usando uma integração
