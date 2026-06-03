# Compute Engine e2-micro hospedando a Evolution API (passo 4).

resource "random_password" "evolution_api_key" {
  length  = 40
  special = false
}

# Guarda a API key da Evolution no Secret Manager (usada pelo agente para responder).
resource "google_secret_manager_secret" "evolution_api_key" {
  secret_id = "EVOLUTION_API_KEY"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "evolution_api_key" {
  secret      = google_secret_manager_secret.evolution_api_key.id
  secret_data = random_password.evolution_api_key.result
}

resource "google_compute_instance" "evolution" {
  name         = "${local.name}-evolution-${local.env}"
  machine_type = "e2-micro"
  zone         = var.zone
  tags         = ["evolution"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 20
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.subnet.id
    access_config {} # IP publico efemero para receber conexoes do WhatsApp
  }

  # Nota: o webhook NAO e configurado aqui (evitar ciclo VM <-> Cloud Run).
  # Ele e definido por instancia, apos o deploy, via API da Evolution
  # (POST /webhook/set/{instance} com o header x-webhook-token) — ver
  # docs/creating-a-new-agent.md.
  metadata = {
    evolution-api-key = random_password.evolution_api_key.result
  }

  metadata_startup_script = file("${path.module}/evolution_startup.sh")

  depends_on = [google_compute_router_nat.nat]
}
