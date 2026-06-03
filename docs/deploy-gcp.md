# Deploy no GCP — passo a passo sequencial

Guia para subir todo o sistema no GCP via **CLI/Terraform** (zero console). Os
passos são **sequenciais e dependentes**: não pule etapas — não dá, por exemplo,
para aplicar o schema antes do Cloud SQL existir, nem buildar a imagem antes do
repositório.

> **Status:** os comandos refletem fielmente o código (`infra/terraform/`,
> `infra/cloudbuild-image.yaml`, `scripts/init_db.sql`). Os **estágios 0–5 são
> diretos**. Os passos de **schema, ingestão e Evolution (6–9)** dependem do
> ambiente real e estão marcados com ⚠️ — são os pontos a confirmar na primeira
> execução. Faremos isso juntos quando você decidir subir.

Recomendação: faça **primeiro no workspace `dev`** (barato, escala a zero, fácil
de destruir). Depois de validar, promova para `prod` (passo 10).

---

## 0. Pré-requisitos

```bash
# gcloud autenticado + Application Default Credentials
gcloud auth login
gcloud config set project SEU_PROJECT_ID
gcloud auth application-default login

# Terraform — pelo tap da HashiCorp (o "brew install terraform" foi descontinuado)
brew install hashicorp/tap/terraform
terraform version    # confirme: v1.x
```

**Permissões IAM** necessárias na sua conta (no projeto): `roles/editor` +
`roles/iam.serviceAccountAdmin` + `roles/resourcemanager.projectIamAdmin`. E
**billing ativo** no projeto.

**Verificação:**
```bash
gcloud projects get-iam-policy SEU_PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:SEU_EMAIL" --format="value(bindings.role)"
```

---

## 1. Preparar as variáveis (`dev.tfvars`)

```bash
cd infra/terraform
cp dev.tfvars.example dev.tfvars
```

Edite `dev.tfvars`:

```hcl
project_id          = "SEU_PROJECT_ID"
region              = "southamerica-east1"
zone                = "southamerica-east1-a"
db_password         = "GERE_UMA_SENHA_FORTE"     # ex.: openssl rand -base64 24
admin_cidrs         = ["35.235.240.0/20"]        # faixa do IAP (acesso por túnel)
model_armor_enabled = false                       # 1º deploy sem Model Armor
gemini_model        = "gemini-2.5-flash"
external_secrets    = []
```

> `admin_cidrs` com a faixa do **IAP** (`35.235.240.0/20`) significa que você
> acessa a VM por túnel do Google (passo 8), sem expor seu IP. O `.tfvars` é
> gitignored — a senha não vai para o GitHub.

---

## 2. Inicializar o Terraform e criar o workspace `dev`

```bash
terraform init
terraform workspace new dev      # isola o state do ambiente dev
terraform validate               # deve dizer: Success! The configuration is valid.
```

---

## 3. Estágio 1 — APIs + Artifact Registry

**Por quê primeiro:** para buildar a imagem (passo 4) precisamos do repositório de
imagens; e nada funciona sem as APIs habilitadas.

```bash
terraform apply \
  -target=google_project_service.apis \
  -target=google_artifact_registry_repository.images \
  -var-file=dev.tfvars
```

Confirme com `yes`. Habilita ~13 APIs (Vertex, Cloud Run, Cloud SQL, Pub/Sub,
Secret Manager, Artifact Registry, Cloud Build, Compute, VPC, Scheduler, Model
Armor) e cria o repositório `agent-images`. **Espere `Apply complete!`.**

---

## 4. Estágio 2 — Buildar e publicar a imagem

**Por quê:** os serviços do Cloud Run referenciam `agent:dev-latest`, que precisa
existir antes do apply completo.

```bash
cd ../..                      # raiz do repositório
gcloud builds submit \
  --config infra/cloudbuild-image.yaml \
  --substitutions=_TAG=dev-latest .
```

O Cloud Build builda o `infra/Dockerfile` e publica a imagem no Artifact Registry.
Leva ~3–5 min. **Verificação:**

```bash
gcloud artifacts docker images list \
  southamerica-east1-docker.pkg.dev/SEU_PROJECT_ID/agent-images/agent
```

---

## 5. Estágio 3 — Aplicar toda a infraestrutura

```bash
cd infra/terraform
terraform apply -var-file=dev.tfvars
```

Cria, na ordem de dependência (o Terraform resolve sozinho): VPC + connector +
NAT, Service Accounts + IAM, Cloud SQL (privado), Memorystore (Redis), Pub/Sub
(+ DLQ), segredos, VM da Evolution, os dois serviços Cloud Run e o Cloud
Scheduler. **Leva ~15–20 min** (Cloud SQL e o peering de rede são os mais lentos).

Ao final, guarde os outputs:

```bash
terraform output                      # webhook_url, evolution_external_ip, db_connection_name...
terraform output -raw webhook_token   # token do webhook (sensível)
terraform output -raw evolution_api_key
```

---

## 6. ⚠️ Aplicar o schema no Cloud SQL

O Cloud SQL sobe **sem IP público** (só rede privada). Para aplicar o
`scripts/init_db.sql`, rode **de dentro da VPC** — a VM da Evolution serve para
isso (ela está na mesma rede e tem Docker).

```bash
# IP privado do Cloud SQL
DB_IP=$(gcloud sql instances describe agent-db-dev --format='value(ipAddresses[0].ipAddress)')

# copiar o schema para a VM (via túnel IAP)
gcloud compute scp scripts/init_db.sql agent-evolution-dev:/tmp/init_db.sql \
  --zone southamerica-east1-a --tunnel-through-iap

# aplicar o schema rodando psql num container na VM
gcloud compute ssh agent-evolution-dev --zone southamerica-east1-a --tunnel-through-iap \
  --command "docker run --rm -i -e PGPASSWORD='SUA_DB_PASSWORD' postgres:15 \
    psql -h ${DB_IP} -U agent -d agent < /tmp/init_db.sql"
```

> Este é o passo mais provável de precisar de ajuste fino na 1ª execução
> (caminho do `psql`, IP, permissões). Alternativa para produção: empacotar
> schema + ingestão como um **Cloud Run Job** que roda dentro da VPC.

---

## 7. ⚠️ Ingerir a base de conhecimento

Mesma lógica: a ingestão precisa de acesso ao banco (rede privada) e da Vertex AI.
O caminho direto é rodar o `ingest.py` de um ambiente com acesso à VPC. Para o
primeiro teste, o mais simples é a partir da VM (instalando Python + deps) ou via
um Cloud Run Job. **Definiremos o método exato na execução real** e fixaremos
aqui.

```bash
# (a confirmar) exemplo conceitual, de dentro da VPC:
# PYTHONPATH=. python scripts/ingest.py --csv knowledge/default.csv --agent-id default
```

---

## 8. Parear a Evolution e configurar o webhook

A Evolution já está rodando na VM. Acesse a API dela (use o `evolution_api_key` e
o IP do output `evolution_external_ip`):

```bash
EVO=http://EVOLUTION_IP:8080
KEY=$(terraform output -raw evolution_api_key)
TOKEN=$(terraform output -raw webhook_token)
WEBHOOK=$(terraform output -raw webhook_url)   # .../webhook

# criar a instância
curl -X POST $EVO/instance/create -H "apikey: $KEY" -H 'Content-Type: application/json' \
  -d '{"instanceName":"default","integration":"WHATSAPP-BAILEYS"}'

# parear o número (retorna o QR Code)
curl $EVO/instance/connect/default -H "apikey: $KEY"

# apontar o webhook desta instância para o Cloud Run, COM o token de autenticação
curl -X POST $EVO/webhook/set/default -H "apikey: $KEY" -H 'Content-Type: application/json' \
  -d "{\"url\":\"$WEBHOOK\",\"enabled\":true,\"events\":[\"MESSAGES_UPSERT\",\"CONNECTION_UPDATE\"],\"headers\":{\"x-webhook-token\":\"$TOKEN\"}}"
```

> Se a manager UI (`:8080`/`:3000`) não abrir do seu navegador, use um túnel IAP:
> `gcloud compute start-iap-tunnel agent-evolution-dev 8080 --local-host-port=localhost:8080 --zone southamerica-east1-a`.

---

## 9. Validar de ponta a ponta

Mande uma mensagem ao número pareado e acompanhe os logs do processador:

```bash
gcloud run services logs read agent-processor-dev --region southamerica-east1
```

Você deve ver `RAG retrieve` → (opcional `Tool executada`) → `Turno concluido`, e
a resposta chegar no WhatsApp.

---

## 10. Promover para produção

```bash
cp prod.tfvars.example prod.tfvars     # ajuste db_tier, admin_cidrs, etc.
terraform workspace new prod
# build da imagem com a tag de prod:
gcloud builds submit --config ../cloudbuild-image.yaml --substitutions=_TAG=prod-latest ../..
terraform apply -var-file=prod.tfvars
```

Diferenças automáticas em prod (ver `infra/terraform/versions.tf`):
`min-instances=1` (sem cold start), Cloud SQL regional com backup + PITR e
`deletion_protection` ligado.

---

## 11. Operação e teardown

```bash
# logs
gcloud run services logs read agent-processor-dev --region southamerica-east1

# CI/CD contínuo (build + deploy a cada push) — ver infra/cloudbuild.yaml

# destruir o ambiente de teste (zera custo)
terraform destroy -var-file=dev.tfvars
```

> Em dev, a stack tem recursos contínuos (Cloud SQL ~$7, Memorystore ~$16,
> Compute e2-micro ~$7/mês). Rode `terraform destroy` ao terminar o teste.

---

## Checklist de segurança antes de prod

- [ ] Webhook autenticado (header `x-webhook-token` configurado na Evolution).
- [ ] `admin_cidrs` restrito (IAP + IPs do time), nunca `0.0.0.0/0`.
- [ ] `model_armor_enabled=true` em prod (guardrails de IA).
- [ ] Cloud SQL e Redis sem IP público (default do Terraform).
- [ ] Segredos só no Secret Manager; credenciais GCP via IAM.
