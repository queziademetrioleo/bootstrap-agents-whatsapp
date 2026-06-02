# Habilita as APIs necessarias (passo 1 da ordem de execucao).
locals {
  gcp_apis = [
    "aiplatform.googleapis.com",        # Vertex AI
    "run.googleapis.com",               # Cloud Run
    "sqladmin.googleapis.com",          # Cloud SQL
    "redis.googleapis.com",             # Memorystore
    "pubsub.googleapis.com",            # Pub/Sub
    "secretmanager.googleapis.com",     # Secret Manager
    "artifactregistry.googleapis.com",  # Artifact Registry
    "cloudbuild.googleapis.com",        # Cloud Build
    "cloudscheduler.googleapis.com",    # Cloud Scheduler (sweep de follow-ups)
    "compute.googleapis.com",           # Compute Engine + VPC
    "vpcaccess.googleapis.com",         # VPC connector
    "servicenetworking.googleapis.com", # Private services access (Cloud SQL/Redis)
  ]
}

resource "google_project_service" "apis" {
  for_each                   = toset(local.gcp_apis)
  service                    = each.value
  disable_on_destroy         = false
  disable_dependent_services = false
}
