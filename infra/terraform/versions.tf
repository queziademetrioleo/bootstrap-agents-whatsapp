terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Recomendado: backend GCS para o state (descomente e ajuste o bucket).
  # backend "gcs" {
  #   bucket = "SEU_BUCKET_TFSTATE"
  #   prefix = "whatsapp-agent"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# Sufixo de ambiente vem do workspace do Terraform (dev | prod).
locals {
  env             = terraform.workspace == "default" ? "dev" : terraform.workspace
  name            = "agent"
  is_prod         = local.env == "prod"
  min_instances   = local.is_prod ? 1 : 0
  db_backup       = local.is_prod
}
