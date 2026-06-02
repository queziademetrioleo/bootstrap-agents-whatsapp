"""Follow-up — re-engajamento por cadencia de stages.

Modelo (inspirado no padrao "last_interaction + job de minuto em minuto"):
  - `conversation_state` guarda, por conversa (instance+phone): a ultima
    interacao do usuario, o proximo stage a enviar e `next_followup_at`
    (quando o proximo follow-up vence, pre-calculado).
  - Um sweep (Cloud Scheduler -> /tasks/followups/sweep) roda periodicamente,
    reivindica de forma atomica as linhas vencidas e dispara.

Config por agente (em agent_configs.config -> "followup"):
  {
    "enabled": true,
    "stages": [
      {"after_minutes": 60,   "mode": "fixed",   "message": "Ainda posso ajudar?"},
      {"after_minutes": 1440, "mode": "summary"},
      {"after_minutes": 4320, "mode": "fixed",   "message": "Vou encerrar por aqui!"}
    ]
  }

Modos de stage:
  - "fixed"   -> envia o texto literal de `message`.
  - "summary" -> gera uma mensagem contextual via Gemini, a partir do resumo do
                 historico da conversa daquele usuario.

`after_minutes` e o silencio relativo ao evento anterior: ultima msg do usuario
(stage 0) ou ultimo follow-up enviado (stages seguintes).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from google.genai import types

from agent import db, evolution, memory
from agent.config import get_settings
from agent.genai_client import get_client
from agent.logging_config import get_logger
from agent.models import AgentConfig

log = get_logger(__name__)


def _stages(cfg: AgentConfig | None) -> list[dict]:
    if cfg is None:
        return []
    fu = cfg.config.get("followup") or {}
    if not fu.get("enabled"):
        return []
    return list(fu.get("stages") or [])


# --------------------------------------------------------- agendamento (write) --


async def on_user_message(
    cfg: AgentConfig, user_id: int, instance_name: str, phone: str
) -> None:
    """Reinicia a cadencia quando o usuario manda mensagem (responde -> reseta).

    Agenda o stage 0 se o follow-up estiver ativo; senao deixa pausado.
    """
    stages = _stages(cfg)
    now = datetime.now(timezone.utc)

    if not stages:
        next_at = None
        paused = True
    else:
        next_at = now + timedelta(minutes=float(stages[0]["after_minutes"]))
        paused = False

    await db.execute(
        """INSERT INTO conversation_state
             (instance_name, phone, user_id, agent_id, last_interaction_at,
              followup_stage, next_followup_at, last_followup_at, followup_paused, updated_at)
           VALUES ($1,$2,$3,$4,$5,0,$6,NULL,$7,$5)
           ON CONFLICT (instance_name, phone) DO UPDATE SET
             user_id = EXCLUDED.user_id,
             agent_id = EXCLUDED.agent_id,
             last_interaction_at = EXCLUDED.last_interaction_at,
             followup_stage = 0,
             next_followup_at = EXCLUDED.next_followup_at,
             last_followup_at = NULL,
             followup_paused = EXCLUDED.followup_paused,
             updated_at = EXCLUDED.updated_at""",
        instance_name, phone, user_id, cfg.agent_id, now, next_at, paused,
    )


# ------------------------------------------------------------------ sweep ------

# Claim atomico: reivindica linhas vencidas e empurra `next_followup_at` por um
# lease (backoff) para que sweeps concorrentes nao peguem a mesma linha. O envio
# (rede) acontece FORA de qualquer lock. Apos sucesso, o stage e avancado.
_CLAIM_SQL = """
UPDATE conversation_state cs
SET next_followup_at = now() + make_interval(mins => $2),
    updated_at = now()
WHERE (cs.instance_name, cs.phone) IN (
    SELECT instance_name, phone FROM conversation_state
    WHERE next_followup_at IS NOT NULL
      AND next_followup_at <= now()
      AND NOT followup_paused
    ORDER BY next_followup_at
    LIMIT $1
    FOR UPDATE SKIP LOCKED
)
RETURNING cs.instance_name, cs.phone, cs.user_id, cs.agent_id, cs.followup_stage;
"""


async def run_sweep() -> int:
    """Dispara os follow-ups vencidos. Retorna quantos foram enviados.

    Tambem aproveita a passada para limpar idempotencia antiga (housekeeping).
    """
    s = get_settings()
    await memory.cleanup_processed(s.processed_retention_days)
    rows = await db.fetch(_CLAIM_SQL, s.followup_sweep_batch, s.followup_lease_minutes)
    sent = 0
    for r in rows:
        try:
            if await _fire(r["instance_name"], r["phone"], r["user_id"], r["followup_stage"]):
                sent += 1
        except Exception:  # noqa: BLE001 — o lease garante o retry no proximo sweep
            log.exception("Falha ao disparar follow-up")
    if rows:
        log.info("Follow-up sweep", extra={"fields": {"claimed": len(rows), "sent": sent}})
    return sent


async def _fire(instance_name: str, phone: str, user_id: int, stage: int) -> bool:
    cfg = await memory.get_agent_config(instance_name)
    stages = _stages(cfg)
    if not stages or stage >= len(stages):
        await _pause(instance_name, phone)
        return False

    stage_def = stages[stage]
    mode = stage_def.get("mode", "fixed")
    if mode == "summary":
        text = await _summary_message(cfg, user_id)
    else:
        text = (stage_def.get("message") or "").strip()

    advanced = False
    if text:
        await evolution.send_text(instance_name, phone, text)
        await memory.save_turn(user_id, "agent", text)
        advanced = True

    await _advance(instance_name, phone, stage, stages)
    return advanced


async def _advance(instance_name: str, phone: str, stage: int, stages: list[dict]) -> None:
    now = datetime.now(timezone.utc)
    new_stage = stage + 1
    if new_stage < len(stages):
        next_at = now + timedelta(minutes=float(stages[new_stage]["after_minutes"]))
        await db.execute(
            """UPDATE conversation_state
               SET followup_stage=$3, next_followup_at=$4, last_followup_at=$5,
                   followup_paused=false, updated_at=$5
               WHERE instance_name=$1 AND phone=$2""",
            instance_name, phone, new_stage, next_at, now,
        )
    else:
        await db.execute(
            """UPDATE conversation_state
               SET followup_stage=$3, next_followup_at=NULL, last_followup_at=$4,
                   followup_paused=true, updated_at=$4
               WHERE instance_name=$1 AND phone=$2""",
            instance_name, phone, new_stage, now,
        )


async def _pause(instance_name: str, phone: str) -> None:
    await db.execute(
        """UPDATE conversation_state
           SET followup_paused=true, next_followup_at=NULL, updated_at=now()
           WHERE instance_name=$1 AND phone=$2""",
        instance_name, phone,
    )


async def _summary_message(cfg: AgentConfig, user_id: int) -> str:
    """Gera um follow-up contextual a partir do resumo do historico (modo summary)."""
    s = get_settings()
    history = await memory.recent_long_history(user_id, limit=20)
    if not history:
        return ""
    convo = "\n".join(
        f"{'Usuario' if t.role == 'user' else 'Agente'}: {t.content}" for t in history
    )
    system = (
        cfg.system_prompt
        + "\n\n## Tarefa de follow-up\n"
        "O usuario parou de responder ha um tempo. Gere UMA mensagem curta, "
        "cordial e natural para retomar a conversa, com base no historico. "
        "Referencie o assunto tratado, nao seja insistente e nao repita saudacoes "
        "genericas. Responda apenas com a mensagem, sem aspas."
    )
    resp = get_client().models.generate_content(
        model=s.gemini_model,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=convo)])],
        config=types.GenerateContentConfig(system_instruction=system, temperature=0.6),
    )
    return (resp.text or "").strip()
