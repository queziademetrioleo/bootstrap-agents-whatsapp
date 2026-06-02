# Agrupamento de mensagens (debounce)

No WhatsApp é comum o usuário mandar várias mensagens seguidas, quebradas em
bolhas:

```
olá
tudo bem?
tenho uma dúvida sobre meu pedido...
```

Cada bolha chega como um evento separado. **Sem agrupamento, o agente
responderia 3 vezes** — atropelado e sem ver a mensagem completa. O template
resolve isso com **debounce por janela de silêncio**.

## Como funciona

Implementação: **`asyncio.sleep` + buffer no Redis** (zero infra extra). Lógica
em `agent/buffer.py`, acionada no `/pubsub/push` (`agent/app.py`).

```
Cada bolha que chega:
  1. should_buffer() -> RPUSH no buffer Redis + grava "marcador" = message_id
  2. asyncio.sleep(DEBOUNCE_SECONDS)        # espera a janela de silêncio
  3. is_latest()? -> o marcador ainda é o meu message_id?
        - SIM  -> ninguém mandou nada depois -> FLUSH (junta tudo, 1 processamento)
        - NÃO  -> chegou bolha mais nova -> sai sem fazer nada (ela fará o flush)
```

Mandando 1 ou 7 bolhas, **só a última** dispara o processamento. O agente recebe
o texto inteiro de uma vez → **uma chamada ao Gemini, uma resposta coerente**.
As bolhas são unidas com quebra de linha, na ordem de chegada.

## Configuração

| Variável | Padrão | O que faz |
|---|---|---|
| `DEBOUNCE_SECONDS` | `8` | Janela de silêncio. **`0` desabilita** (processa cada bolha na hora). |
| `DEBOUNCE_BUFFER_TTL_SECONDS` | `300` | TTL do buffer no Redis (limpeza de órfãos). |

Diminua para responder mais rápido (arrisca cortar o usuário no meio); aumente
para agrupar melhor (o usuário sente mais a demora). 5–10s é o usual.

## Dedup (entrega at-least-once do Pub/Sub)

O Pub/Sub pode reentregar a mesma bolha. Dois guardas evitam duplicação:

- **Duplicata dentro da janela** → SET no Redis (`SADD` idempotente).
- **Duplicata após o flush** → `processed_messages` no Postgres, marcado **só
  após** o processamento dar certo (se falhar e o Pub/Sub reentregar, reprocessa
  sem perder a mensagem).

O `core.process_message` é chamado com `check_idempotency=False` no caminho do
flush, porque as bolhas já foram dedupadas antes de serem agrupadas.

## Considerações de Cloud Run

- O request fica vivo durante o `sleep` (até `DEBOUNCE_SECONDS`). Isso **segura a
  instância** pela janela — custo pequeno, aceitável em volume baixo/médio.
- A janela (8s) é **bem menor** que o `ack_deadline` do Pub/Sub (60s) e que o
  timeout do Cloud Run (300s), então não há risco de ack expirar.
- Em dev (`min-instances=0`), a instância não escala a zero enquanto há um request
  dormindo — comportamento esperado.

## Quando trocar por Cloud Tasks

Se o volume crescer muito (muitas conversas simultâneas segurando instâncias por
8s cada), vale migrar o "timer" para **Cloud Tasks** (callback HTTP agendado, sem
segurar instância). O buffer no Redis continua igual; só o gatilho muda. Veja a
discussão de trade-offs no histórico do projeto.
