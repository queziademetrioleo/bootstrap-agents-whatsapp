variable "project_id" {
  type        = string
  description = "ID do projeto GCP."
}

variable "region" {
  type        = string
  default     = "southamerica-east1"
  description = "Regiao principal (Cloud Run, Cloud SQL, Vertex AI)."
}

variable "zone" {
  type        = string
  default     = "southamerica-east1-a"
  description = "Zona para o Compute Engine da Evolution."
}

variable "db_password" {
  type        = string
  sensitive   = true
  description = "Senha do usuario do banco do agente."
}

variable "db_tier" {
  type        = string
  default     = "db-f1-micro"
  description = "Tier do Cloud SQL (~$7/mes no f1-micro)."
}

variable "redis_memory_gb" {
  type        = number
  default     = 1
  description = "Tamanho do Memorystore Basic em GB."
}

variable "evolution_image" {
  type        = string
  default     = "evoapicloud/evolution-api:latest"
  description = "Imagem Docker da Evolution API."
}

variable "image_tag" {
  type        = string
  default     = "dev-latest"
  description = "Tag da imagem do agente a deployar no Cloud Run."
}

variable "github_owner" {
  type        = string
  default     = ""
  description = "Owner do repo GitHub para o trigger do Cloud Build (opcional)."
}

variable "github_repo" {
  type        = string
  default     = ""
  description = "Nome do repo GitHub para o trigger do Cloud Build (opcional)."
}

variable "external_secrets" {
  type        = list(string)
  default     = []
  description = "Nomes de segredos de APIs externas a criar no Secret Manager (ex.: CRM_API_TOKEN)."
}

variable "followup_sweep_schedule" {
  type        = string
  default     = "* * * * *"
  description = "Cron do Cloud Scheduler para o sweep de follow-ups (default: a cada minuto)."
}
