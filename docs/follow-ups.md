# Follow-up (re-engajamento)

O agente pode mandar mensagens de follow-up quando o usuário some, em **stages**
com cadência crescente. É **por agente** (cada cliente configura o seu) e pode
ficar ligado ou desligado.

## Como funciona (o mecanismo)

Inspirado no padrão "guardar a última interação + um job de minuto em minuto":

- A tabela `conversation_state` guarda, por conversa (`instance` + `phone`):
  `last_interaction_at`, o `followup_stage` atual e `next_followup_at`
  (quando o próximo follow-up vence, **pré-calculado**).
- Um **Cloud Scheduler** (cron, default a cada minuto) chama
  `POST /tasks/followups/sweep`. O sweep reivindica de forma **atômica**
  (`FOR UPDATE SKIP LOCKED` + lease) as conversas com `next_followup_at <= now()`
  e dispara — seguro com múltiplas instâncias.
- Quando o usuário responde, a cadência **reinicia do stage 0**
  (`core.process_message` chama `followup.on_user_message`).

## Configuração (por agente)

Fica em `agent_configs.config["followup"]`:

```json
{
  "enabled": true,
  "stages": [
    { "after_minutes": 60,   "mode": "fixed",   "message": "Oi! Ainda posso te ajudar? 😊" },
    { "after_minutes": 1440, "mode": "summary" },
    { "after_minutes": 4320, "mode": "fixed",   "message": "Vou encerrar por aqui, qualquer coisa é só chamar!" }
  ]
}
```

- **`enabled`** — liga/desliga o follow-up.
- **`stages`** — a **quantidade** de follow-ups é o tamanho do array.
- **`after_minutes`** — silêncio (em minutos) relativo ao evento anterior: última
  mensagem do usuário (stage 0) ou último follow-up enviado (stages seguintes).
- **`mode`** por stage:
  - `"fixed"` → envia o texto de `message` literal.
  - `"summary"` → gera uma mensagem contextual via Gemini, a partir do **resumo
    do histórico** daquela conversa (retoma o assunto, sem ser insistente).

### Definindo na criação do agente

```bash
python scripts/create_agent.py \
  --instance loja-acme --agent-id acme \
  --system-prompt "Voce e a atendente da Loja Acme..." \
  --tools check_order_status \
  --followup '{"enabled":true,"stages":[
      {"after_minutes":60,"mode":"fixed","message":"Ainda posso te ajudar?"},
      {"after_minutes":1440,"mode":"summary"}
  ]}'
```

Para **desligar**, use `"enabled": false` (ou simplesmente não defina o bloco).

## Variáveis do mecanismo (globais)

| Variável | Padrão | O que faz |
|---|---|---|
| `followup_sweep_schedule` (Terraform) | `* * * * *` | cron do sweep (a cada minuto) |
| `SCHEDULER_SA_EMAIL` | (do Terraform) | SA do Scheduler autorizada no endpoint |
| `FOLLOWUP_SWEEP_BATCH` | `100` | conversas reivindicadas por sweep |
| `FOLLOWUP_LEASE_MINUTES` | `10` | lease/backoff ao reivindicar (anti corrida) |

## Garantias e detalhes

- **Reset ao responder:** qualquer mensagem do usuário zera a cadência (stage 0).
- **Multi-instância:** o claim atômico + lease impedem dois sweeps de enviarem o
  mesmo follow-up.
- **Retry-safe:** se o envio falhar, o lease faz a conversa ser tentada de novo no
  próximo sweep (o stage só avança após o envio dar certo).
- **Esgotou os stages:** a conversa é pausada (`followup_paused = true`) até o
  usuário voltar a interagir.
- **`summary` sem histórico:** se não houver histórico, nenhum texto é gerado e o
  stage apenas avança.

## Trocar a frequência

Edite `followup_sweep_schedule` no `*.tfvars` (ex.: `"*/5 * * * *"` para a cada 5
min) — a latência máxima de um follow-up é o intervalo do cron, irrelevante para
janelas de horas/dias.
