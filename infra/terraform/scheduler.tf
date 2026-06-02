# Cloud Scheduler — dispara o sweep de follow-ups periodicamente.
# "Job de minuto em minuto" batendo no /tasks/followups/sweep do processador,
# autenticado por OIDC (SA dedicada com run.invoker no servico).

resource "google_service_account" "scheduler_invoker" {
  account_id   = "agent-scheduler-inv"
  display_name = "Cloud Scheduler follow-up invoker"
}

resource "google_cloud_run_v2_service_iam_member" "scheduler_invoke" {
  name     = google_cloud_run_v2_service.processor.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler_invoker.email}"
}

resource "google_cloud_scheduler_job" "followup_sweep" {
  name             = "${local.name}-followup-sweep-${local.env}"
  region           = var.region
  schedule         = var.followup_sweep_schedule
  time_zone        = "America/Sao_Paulo"
  attempt_deadline = "320s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.processor.uri}/tasks/followups/sweep"

    oidc_token {
      service_account_email = google_service_account.scheduler_invoker.email
      audience              = google_cloud_run_v2_service.processor.uri
    }
  }

  depends_on = [google_project_service.apis]
}
