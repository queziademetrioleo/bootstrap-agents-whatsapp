# Model Armor — guardrails de IA (P4).
# Cria o template com os filtros; o app (agent/guardrails.py) chama
# sanitizeUserPrompt / sanitizeModelResponse contra ele.
#
# NOTA: o recurso google_model_armor_template requer provider google >= ~6.x.
# Os nomes dos enums seguem a API do Model Armor; ajuste o confidence_level se a
# sua regiao/versao do provider divergir.

resource "google_model_armor_template" "guardrail" {
  count       = var.model_armor_enabled ? 1 : 0
  location    = var.region
  template_id = var.model_armor_template_id

  filter_config {
    # Responsible AI: conteudo perigoso, odio, sexual, assedio.
    rai_settings {
      rai_filters {
        filter_type      = "DANGEROUS"
        confidence_level = "MEDIUM_AND_ABOVE"
      }
      rai_filters {
        filter_type      = "HATE_SPEECH"
        confidence_level = "MEDIUM_AND_ABOVE"
      }
      rai_filters {
        filter_type      = "SEXUALLY_EXPLICIT"
        confidence_level = "MEDIUM_AND_ABOVE"
      }
      rai_filters {
        filter_type      = "HARASSMENT"
        confidence_level = "MEDIUM_AND_ABOVE"
      }
    }

    # Prompt injection e jailbreak — o filtro central deste guardrail.
    pi_and_jailbreak_filter_settings {
      filter_enforcement = "ENABLED"
      confidence_level   = "LOW_AND_ABOVE"
    }

    # URLs maliciosas em prompts/respostas.
    malicious_uri_filter_settings {
      filter_enforcement = "ENABLED"
    }
  }

  depends_on = [google_project_service.apis]
}
