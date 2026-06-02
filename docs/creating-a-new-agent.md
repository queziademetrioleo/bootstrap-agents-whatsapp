# Como criar um novo agente (novo cliente)

Um agente novo **não** exige novo repositório nem novo serviço. Tudo roda no mesmo
Cloud Run, roteado pelo `instance_name` que chega no webhook. Criar um agente são
3 passos.

## 1. Criar a instância na Evolution (número de WhatsApp)

A Evolution roda na VM (Compute Engine). Use a API REST dela (IP no output
`evolution_external_ip`, API key no output `evolution_api_key`):

```bash
EVO=http://EVOLUTION_IP:8080
KEY=SUA_API_KEY

# criar a instância
curl -X POST $EVO/instance/create -H "apikey: $KEY" -H 'Content-Type: application/json' \
  -d '{"instanceName":"loja-acme","integration":"WHATSAPP-BAILEYS"}'

# parear o número (abre QR Code)
curl $EVO/instance/connect/loja-acme -H "apikey: $KEY"

# apontar o webhook desta instância para o Cloud Run
curl -X POST $EVO/webhook/set/loja-acme -H "apikey: $KEY" -H 'Content-Type: application/json' \
  -d '{"url":"https://SEU_WEBHOOK_URL/webhook","enabled":true,"events":["MESSAGES_UPSERT","CONNECTION_UPDATE"]}'
```

> O `instanceName` (`loja-acme`) é a **identidade do agente** — ele chega no webhook
> e é usado para carregar a config certa.

## 2. Registrar a config do agente

Um registro em `agent_configs` define persona + tools ativas:

```bash
python scripts/create_agent.py \
  --instance loja-acme \
  --agent-id acme \
  --system-prompt "Voce e a atendente virtual da Loja Acme. Responda em portugues, cordial e objetiva. Use a base de conhecimento e nao invente informacoes." \
  --tools check_order_status
```

- `--instance`: o mesmo `instanceName` da Evolution.
- `--agent-id`: isola a base de conhecimento (passo 3). Pode ser igual ao instance.
- `--tools`: tools de domínio/integração a ativar (as `universal` já entram sozinhas).

## 3. Subir a base de conhecimento do agente

```bash
# crie knowledge/acme.csv com as colunas Pergunta,Resposta
python scripts/ingest.py --csv knowledge/acme.csv --agent-id acme
```

## Pronto

Mande uma mensagem para o número pareado. O fluxo:

```
WhatsApp(loja-acme) → Evolution → webhook → Pub/Sub → processador
   → carrega agent_config de 'loja-acme' (persona + tools)
   → RAG na base 'acme'
   → Gemini responde → volta pelo WhatsApp
```

## Atualizar um agente existente

`create_agent.py` faz upsert: rode de novo com os novos valores para trocar a
persona ou as tools. Para a base de conhecimento, edite o CSV e rode `ingest.py`.
