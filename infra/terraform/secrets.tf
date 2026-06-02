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
