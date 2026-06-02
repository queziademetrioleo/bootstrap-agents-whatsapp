# Como adicionar uma integração com API externa

Integrações ficam em `integrations/` — uma por arquivo. Elas encapsulam o acesso
a uma API de terceiro (CRM, ERP, Google Calendar, planilhas...) e expõem funções
que as **tools** importam. O cliente HTTP base já traz timeout, retry e leitura
de credenciais — você não reimplementa nada disso.

## 1. Criar o arquivo da integração

```python
# integrations/meu_crm.py
import os
from functools import lru_cache
from integrations.base import HttpClient, secret
from agent.tool_base import ToolContext

@lru_cache
def _client() -> HttpClient:
    base_url = os.environ["MEU_CRM_BASE_URL"]          # config por env
    token = secret("MEU_CRM_TOKEN")                    # segredo via Secret Manager
    return HttpClient(base_url, default_headers={"Authorization": f"Bearer {token}"})

async def buscar_cliente(ctx: ToolContext, documento: str) -> dict | None:
    resp = await _client().get(f"/clientes/{documento}")
    if resp.status_code == 404:
        return None
    return resp.json()
```

## 2. Credenciais — nunca hardcoded

Credenciais de APIs externas vivem no **Secret Manager**. A função `secret("NOME")`
resolve assim:

1. se existir uma **variável de ambiente** `NOME` (o Cloud Run monta o segredo como
   env var — forma recomendada), usa ela;
2. senão, busca direto no Secret Manager (`latest`).

### Declarar o segredo na infra

Adicione o nome ao `external_secrets` no seu `*.tfvars`:

```hcl
external_secrets = ["CRM_API_TOKEN", "MEU_CRM_TOKEN"]
```

O Terraform cria o segredo (vazio) e dá `secretAccessor` à SA do agente. Depois,
preencha o valor:

```bash
echo -n "valor-do-token" | gcloud secrets versions add MEU_CRM_TOKEN --data-file=-
```

E exponha como env var no Cloud Run (o `cloudrun.tf` já faz isso para todos os
nomes em `external_secrets`).

## 3. Usar a integração numa tool

```python
# tools/buscar_cliente.py
from agent.tool_base import AgentTool, ToolContext
from integrations import meu_crm

async def _run(ctx: ToolContext, documento: str) -> dict:
    cliente = await meu_crm.buscar_cliente(ctx, documento)
    return {"encontrado": cliente is not None, "cliente": cliente}

TOOL = AgentTool(
    name="buscar_cliente",
    description="Busca os dados de um cliente pelo CPF/CNPJ no CRM.",
    parameters={
        "type": "object",
        "properties": {"documento": {"type": "string", "description": "CPF ou CNPJ"}},
        "required": ["documento"],
    },
    handler=_run,
    category="integration",
)
```

## Padrões do cliente base (`integrations/base.py`)

- `HttpClient(base_url, default_headers=..., timeout=...)`
- `.get(path, **kwargs)` / `.post(path, **kwargs)` — já com retry exponencial (3x).
- `secret(nome)` — leitura cacheada de segredo (env var ou Secret Manager).

Veja `integrations/example_crm.py` para um exemplo completo (com modo simulado).
