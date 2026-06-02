output "environment" {
  value = local.env
}

output "webhook_url" {
  description = "URL do webhook receiver — configure na Evolution (POST /webhook/set)."
  value       = "${google_cloud_run_v2_service.webhook.uri}/webhook"
}

output "processor_url" {
  value = google_cloud_run_v2_service.processor.uri
}

output "evolution_external_ip" {
  description = "IP publico da VM da Evolution (manager UI em :8080)."
  value       = google_compute_instance.evolution.network_interface[0].access_config[0].nat_ip
}

output "evolution_api_key" {
  description = "API key gerada da Evolution (sensivel)."
  value       = random_password.evolution_api_key.result
  sensitive   = true
}

output "webhook_token" {
  description = "Token do webhook — configure na Evolution como header x-webhook-token."
  value       = random_password.webhook_token.result
  sensitive   = true
}

output "db_connection_name" {
  description = "Connection name do Cloud SQL (PROJECT:REGION:INSTANCE)."
  value       = google_sql_database_instance.agent.connection_name
}

output "redis_host" {
  value = google_redis_instance.agent.host
}

output "pubsub_topic" {
  value = google_pubsub_topic.messages.name
}

output "agent_service_account" {
  value = google_service_account.agent.email
}

output "artifact_repo" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}
