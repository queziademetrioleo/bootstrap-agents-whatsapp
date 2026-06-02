# VPC privada + conectividade (passo 3).
# Cloud Run acessa Cloud SQL e Memorystore via rede privada; nenhum dos dois e
# exposto a internet. O Compute Engine da Evolution usa Cloud NAT para saida.

resource "google_compute_network" "vpc" {
  name                    = "${local.name}-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.apis]
}

resource "google_compute_subnetwork" "subnet" {
  name          = "${local.name}-subnet"
  ip_cidr_range = "10.10.0.0/24"
  region        = var.region
  network       = google_compute_network.vpc.id

  private_ip_google_access = true
}

# Conector serverless (Cloud Run -> VPC).
resource "google_vpc_access_connector" "connector" {
  name          = "${local.name}-conn-${local.env}"
  region        = var.region
  network       = google_compute_network.vpc.name
  ip_cidr_range = local.is_prod ? "10.10.2.0/28" : "10.10.1.0/28"
  min_instances = 2
  max_instances = 3
  depends_on    = [google_project_service.apis]
}

# Private Services Access — necessario para Cloud SQL e Memorystore com IP privado.
resource "google_compute_global_address" "private_range" {
  name          = "${local.name}-private-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "private_vpc" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_range.name]
}

# Cloud NAT para o Compute Engine da Evolution (saida sem IP publico fixo).
resource "google_compute_router" "router" {
  name    = "${local.name}-router"
  region  = var.region
  network = google_compute_network.vpc.id
}

resource "google_compute_router_nat" "nat" {
  name                               = "${local.name}-nat"
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

# Firewall da VM da Evolution (P3).
# A VM NAO precisa de inbound da internet para operar: o WhatsApp/Baileys e
# outbound (via Cloud NAT) e o webhook vai da VM PARA o Cloud Run. As portas
# abaixo sao so para ADMIN (manager UI 8080/3000, SSH 22) — restrinja a IPs
# conhecidos via `admin_cidrs`. SSH idealmente via IAP (35.235.240.0/20).
resource "google_compute_firewall" "evolution_admin" {
  name    = "${local.name}-evolution-admin"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["8080", "3000", "22"]
  }
  source_ranges = var.admin_cidrs
  target_tags   = ["evolution"]
}
