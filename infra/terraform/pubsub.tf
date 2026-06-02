# Pub/Sub — fila entre webhook receiver e processador.
# Push autenticado (OIDC) para o Cloud Run do processador, com dead-letter.

resource "google_pubsub_topic" "messages" {
  name       = "${local.name}-messages-${local.env}"
  depends_on = [google_project_service.apis]
}

resource "google_pubsub_topic" "dead_letter" {
  name = "${local.name}-messages-dlq-${local.env}"
}

resource "google_pubsub_subscription" "processor" {
  name  = "${local.name}-processor-${local.env}"
  topic = google_pubsub_topic.messages.id

  ack_deadline_seconds       = 60
  message_retention_duration = "600s"
  enable_message_ordering    = true

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.processor.uri}/pubsub/push"

    oidc_token {
      service_account_email = google_service_account.pubsub_invoker.email
    }
  }

  retry_policy {
    minimum_backoff = "5s"
    maximum_backoff = "120s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }
}

# Permite ao Pub/Sub invocar o Cloud Run do processador via OIDC.
resource "google_cloud_run_v2_service_iam_member" "pubsub_invoke" {
  name     = google_cloud_run_v2_service.processor.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_invoker.email}"
}

# O agente publica no topico (webhook receiver). A SA do agente ja tem
# pubsub.publisher no nivel de projeto (iam.tf); este binding e o de granularidade fina.
resource "google_pubsub_topic_iam_member" "agent_publish" {
  topic  = google_pubsub_topic.messages.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.agent.email}"
}
