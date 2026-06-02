# Cloud SQL PostgreSQL + PgVector (passo 5). Acessivel apenas via VPC privada.

resource "google_sql_database_instance" "agent" {
  name             = "${local.name}-db-${local.env}"
  database_version = "POSTGRES_15"
  region           = var.region

  depends_on = [google_service_networking_connection.private_vpc]

  settings {
    tier              = var.db_tier
    availability_type = local.is_prod ? "REGIONAL" : "ZONAL"
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled    = false # sem IP publico
      private_network = google_compute_network.vpc.id
    }

    backup_configuration {
      enabled                        = local.db_backup
      point_in_time_recovery_enabled = local.db_backup
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }
  }

  deletion_protection = local.is_prod
}

resource "google_sql_database" "agent" {
  name     = "agent"
  instance = google_sql_database_instance.agent.name
}

resource "google_sql_user" "agent" {
  name     = "agent"
  instance = google_sql_database_instance.agent.name
  password = var.db_password
}

# NOTA: a extensao pgvector e o schema sao aplicados via scripts/init_db.sql
# apos a criacao (ver docs/deploying.md) — `CREATE EXTENSION vector;` + tabelas.
