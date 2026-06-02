# Service Accounts e roles (least privilege) — passo 2.

# --- SA do agente (anexada ao Cloud Run, identidade em runtime) ---
resource "google_service_account" "agent" {
  account_id   = "agent-sa"
  display_name = "WhatsApp Agent runtime SA"
}

locals {
  agent_roles = [
    "roles/aiplatform.user",              # Vertex AI (Gemini + embeddings)
    "roles/modelarmor.user",              # Guardrails (sanitize prompt/response)
    "roles/cloudsql.client",              # Cloud SQL via Connector
    "roles/pubsub.publisher",             # publicar (webhook receiver)
    "roles/pubsub.subscriber",            # consumir (processador)
    "roles/secretmanager.secretAccessor", # segredos de APIs externas
  ]
}

resource "google_project_iam_member" "agent_roles" {
  for_each = toset(local.agent_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.agent.email}"
}

# --- SA do CI/CD (usada pelo Cloud Build) ---
resource "google_service_account" "cicd" {
  account_id   = "agent-cicd-sa"
  display_name = "WhatsApp Agent CI/CD SA"
}

resource "google_project_iam_member" "cicd_run" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "cicd_artifact" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

# Permite a SA do CI/CD anexar a SA do agente ao Cloud Run no deploy (obrigatorio).
resource "google_service_account_iam_member" "cicd_actas_agent" {
  service_account_id = google_service_account.agent.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.cicd.email}"
}

# SA usada pelo Pub/Sub para o push autenticado (OIDC) ao processador.
resource "google_service_account" "pubsub_invoker" {
  account_id   = "agent-pubsub-invoker"
  display_name = "Pub/Sub push invoker"
}
