"""Cliente unico do Gen AI SDK (`google-genai`) em modo Vertex AI.

Decisao de SDK (plano, referencia 1): `vertexai.generative_models` foi
depreciado (jun/2025, remocao jun/2026). Usamos `google-genai` com
`vertexai=True`. A autenticacao e por Application Default Credentials — a SA
anexada ao Cloud Run com `roles/aiplatform.user`. Nenhuma API key.
"""

from __future__ import annotations

from functools import lru_cache

from google import genai

from agent.config import get_settings


@lru_cache
def get_client() -> genai.Client:
    s = get_settings()
    return genai.Client(
        vertexai=True,
        project=s.gcp_project_id,
        location=s.gcp_location,
    )
