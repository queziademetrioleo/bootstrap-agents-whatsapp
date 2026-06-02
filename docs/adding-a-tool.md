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

## Ativar uma tool de domínio num agente

Tools `universal` já entram em todos os agentes. Tools `domain`/`integration`
precisam ser listadas no `tools_enabled` do agente:

```bash
python scripts/create_agent.py \
  --instance loja-acme --agent-id acme \
  --system-prompt "..." \
  --tools consultar_clima check_order_status
```

## Testando

Rode o app local (`make run`) e dispare uma mensagem que acione a tool (veja
`docs/local-development.md`). Os logs mostram `Tool executada` com o nome.

## Exemplos no repositório

- `tools/save_user_note.py` — universal
- `tools/search_conversation_history.py` — universal
- `tools/example_check_order_status.py` — domain, usando uma integração
