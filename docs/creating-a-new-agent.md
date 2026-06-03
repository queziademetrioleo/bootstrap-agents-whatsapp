# Configurar o agente deste cliente

**1 repositório = 1 cliente = 1 deploy.** Para um cliente novo você clona o
repositório e configura **três coisas** (persona, base de conhecimento, tools).
Não há tabela de agentes nem roteamento — este clone serve um único cliente.

> Para um segundo cliente, faça outro `git clone` e repita num projeto GCP
> próprio. Nada é compartilhado.

## 1. Editar a persona e as tools (`config/agent.yaml`)

Abra [`config/agent.yaml`](../config/agent.yaml) e defina o agente:

```yaml
instance_name: clinica-x        # nome da instância na Evolution (o número do cliente)

system_prompt: |
  Voce e a atendente virtual da Clinica X. Responda em portugues, de forma
  cordial e objetiva. Use a base de conhecimento e nao invente informacoes.

tools_enabled:
  - check_order_status          # tools de domínio/integração (as universais já entram)

followup:
  enabled: false                # ou true + stages (ver follow-ups.md)
```

## 2. Montar a base de conhecimento (FAQ)

Edite `knowledge/default.csv` (colunas `Pergunta`, `Resposta`) com o FAQ do
cliente e ingira:

```bash
python scripts/ingest.py --csv knowledge/default.csv
```

Detalhes: [updating-knowledge-base.md](updating-knowledge-base.md).

## 3. Criar a instância na Evolution (parear o número)

Após o deploy (ver [deploy-gcp.md](deploy-gcp.md)), a Evolution está rodando na VM.
Crie a instância com o **mesmo `instance_name`** do `agent.yaml` e pareie o número:

```bash
EVO=http://EVOLUTION_IP:8080
KEY=$(terraform -chdir=infra/terraform output -raw evolution_api_key)
TOKEN=$(terraform -chdir=infra/terraform output -raw webhook_token)
WEBHOOK=$(terraform -chdir=infra/terraform output -raw webhook_url)

# criar a instância
curl -X POST $EVO/instance/create -H "apikey: $KEY" -H 'Content-Type: application/json' \
  -d '{"instanceName":"clinica-x","integration":"WHATSAPP-BAILEYS"}'

# parear o número (retorna o QR Code)
curl $EVO/instance/connect/clinica-x -H "apikey: $KEY"

# apontar o webhook para o Cloud Run, COM o token de autenticação
curl -X POST $EVO/webhook/set/clinica-x -H "apikey: $KEY" -H 'Content-Type: application/json' \
  -d "{\"url\":\"$WEBHOOK\",\"enabled\":true,\"events\":[\"MESSAGES_UPSERT\",\"CONNECTION_UPDATE\"],\"headers\":{\"x-webhook-token\":\"$TOKEN\"}}"
```

## Pronto

Mande uma mensagem para o número pareado. O fluxo:

```
WhatsApp → Evolution → webhook → Pub/Sub → processador
   → carrega config/agent.yaml (persona + tools)
   → RAG na base de conhecimento
   → Gemini responde → volta pelo WhatsApp
```

## Atualizar o agente depois

- **Persona / tools / follow-up:** edite `config/agent.yaml`. Em local, reinicie
  o `make run`. Em produção, faça um novo deploy (a config é empacotada na imagem).
- **Base de conhecimento:** edite o CSV e rode `ingest.py` (efeito imediato, sem
  redeploy).
