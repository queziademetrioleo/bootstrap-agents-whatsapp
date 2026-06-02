# Cloud Run — webhook receiver + processador (mesma imagem, dois servicos).
# Roda com a SA do agente. Acessa Cloud SQL/Redis via VPC connector.

locals {
  image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}/agent:${var.image_tag}"

  common_env = {
    ENV                         = local.env
    GCP_PROJECT_ID              = var.project_id
    GCP_LOCATION                = var.region
    GEMINI_MODEL                = var.gemini_model
    DB_INSTANCE_CONNECTION_NAME = google_sql_database_instance.agent.connection_name
    DB_NAME                     = google_sql_database.agent.name
    DB_USER                     = google_sql_user.agent.name
    REDIS_HOST                  = google_redis_instance.agent.host
    REDIS_PORT                  = tostring(google_redis_instance.agent.port)
    PUBSUB_TOPIC                = google_pubsub_topic.messages.name
    PUBSUB_PUSH_SA_EMAIL        = google_service_account.pubsub_invoker.email
    SCHEDULER_SA_EMAIL          = google_service_account.scheduler_invoker.email
    EVOLUTION_BASE_URL          = "http://${google_compute_instance.evolution.network_interface[0].network_ip}:8080"
    USE_CLOUD_SQL               = "true"
    MODEL_ARMOR_ENABLED         = tostring(var.model_armor_enabled)
    MODEL_ARMOR_TEMPLATE        = var.model_armor_enabled ? var.model_armor_template_id : ""
  }

  # Segredos montados como env nos 2 servicos. Sempre inclui a senha do banco, o
  # token do webhook (P1) e a API key da Evolution (P2); soma os externos.
  secret_env_names = concat(
    ["DB_PASSWORD", "EVOLUTION_API_KEY", "WEBHOOK_TOKEN"],
    var.external_secrets,
  )
}

# --- Webhook receiver ---
resource "google_cloud_run_v2_service" "webhook" {
  name     = "${local.name}-webhook-${local.env}"
  location = var.region

  template {
    service_account = google_service_account.agent.email
    scaling {
      min_instance_count = local.min_instances
      max_instance_count = 10
    }

    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = local.image
      ports { container_port = 8080 }

      dynamic "env" {
        for_each = local.common_env
        content {
          name  = env.key
          value = env.value
        }
      }

      # Segredos via Secret Manager (DB, token do webhook, Evolution, externos).
      dynamic "env" {
        for_each = local.secret_env_names
        content {
          name = env.value
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.agent.connection_name]
      }
    }
  }

  depends_on = [google_project_iam_member.agent_roles]
}

# --- Processador (consumidor do Pub/Sub) ---
resource "google_cloud_run_v2_service" "processor" {
  name     = "${local.name}-processor-${local.env}"
  location = var.region

  template {
    service_account = google_service_account.agent.email
    scaling {
      min_instance_count = local.min_instances
      max_instance_count = 10
    }

    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = local.image
      ports { container_port = 8080 }

      dynamic "env" {
        for_each = local.common_env
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = local.secret_env_names
        content {
          name = env.value
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.agent.connection_name]
      }
    }
  }

  depends_on = [google_project_iam_member.agent_roles]
}

# A Evolution (no Compute Engine) precisa chamar o webhook. O Cloud Run recebe
# ingress publico, mas o app valida o token estatico do header `x-webhook-token`
# (P1) em tempo constante — a Evolution e configurada para enviar esse header.
resource "google_cloud_run_v2_service_iam_member" "webhook_public" {
  name     = google_cloud_run_v2_service.webhook.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers" # protegido pelo token do webhook no app (agent/security.py)
}
