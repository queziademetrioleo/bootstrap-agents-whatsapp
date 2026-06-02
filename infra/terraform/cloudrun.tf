# Cloud Run — webhook receiver + processador (mesma imagem, dois servicos).
# Roda com a SA do agente. Acessa Cloud SQL/Redis via VPC connector.

locals {
  image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}/agent:${var.image_tag}"

  common_env = {
    ENV                         = local.env
    GCP_PROJECT_ID              = var.project_id
    GCP_LOCATION                = var.region
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
  }
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

      # Segredos externos (Evolution API key, HMAC, etc) via Secret Manager.
      dynamic "env" {
        for_each = var.external_secrets
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
        for_each = var.external_secrets
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

# A Evolution (no Compute Engine) precisa chamar o webhook. Como o Cloud Run
# exige autenticacao, conceda invoker a SA do agente (a VM usa essa identidade)
# ou exponha o webhook com Cloud Run ingress + token. Para o template, o webhook
# recebe ingress de toda a internet mas valida HMAC no app.
resource "google_cloud_run_v2_service_iam_member" "webhook_public" {
  name     = google_cloud_run_v2_service.webhook.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers" # protegido por HMAC no app (agent/security.py)
}
