# Artifact Registry — imagens Docker do agente (passo 8).

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "agent-images"
  format        = "DOCKER"
  description   = "Imagens do WhatsApp AI Agent"
  depends_on    = [google_project_service.apis]
}

# Cloud Build trigger (opcional — so cria se github_owner/repo forem informados).
resource "google_cloudbuild_trigger" "deploy" {
  count    = var.github_owner != "" && var.github_repo != "" ? 1 : 0
  name     = "${local.name}-deploy-${local.env}"
  location = var.region

  service_account = google_service_account.cicd.id

  github {
    owner = var.github_owner
    name  = var.github_repo
    push {
      branch = local.is_prod ? "^release$" : "^main$"
    }
  }

  filename = "infra/cloudbuild.yaml"

  substitutions = {
    _ENV    = local.env
    _REGION = var.region
    _REPO   = google_artifact_registry_repository.images.repository_id
  }
}
