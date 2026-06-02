# Secret Manager — apenas credenciais de APIs externas de terceiros.
# Credenciais GCP (Vertex, Cloud SQL, Redis) sao por IAM/VPC, nao aqui.
# Os valores sao preenchidos manualmente apos o apply (ver docs/adding-an-integration.md):
#   echo -n "TOKEN" | gcloud secrets versions add CRM_API_TOKEN --data-file=-

resource "google_secret_manager_secret" "external" {
  for_each  = toset(var.external_secrets)
  secret_id = each.value
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

# A SA do agente pode ler cada segredo externo (least privilege por segredo).
resource "google_secret_manager_secret_iam_member" "agent_access" {
  for_each  = google_secret_manager_secret.external
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent.email}"
}

# A SA do agente tambem le a API key da Evolution.
resource "google_secret_manager_secret_iam_member" "agent_evolution_key" {
  secret_id = google_secret_manager_secret.evolution_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent.email}"
}

# --- Token do webhook (P1) ---
# Token estatico que a Evolution envia no header `x-webhook-token`. Autentica a
# origem do webhook publico (o app valida em tempo constante).
resource "random_password" "webhook_token" {
  length  = 40
  special = false
}

resource "google_secret_manager_secret" "webhook_token" {
  secret_id = "WEBHOOK_TOKEN"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "webhook_token" {
  secret      = google_secret_manager_secret.webhook_token.id
  secret_data = random_password.webhook_token.result
}

resource "google_secret_manager_secret_iam_member" "agent_webhook_token" {
  secret_id = google_secret_manager_secret.webhook_token.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent.email}"
}

# --- Senha do banco (injetada como env DB_PASSWORD no Cloud Run) ---
resource "google_secret_manager_secret" "db_password" {
  secret_id = "DB_PASSWORD"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = var.db_password
}

resource "google_secret_manager_secret_iam_member" "agent_db_password" {
  secret_id = google_secret_manager_secret.db_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent.email}"
}
