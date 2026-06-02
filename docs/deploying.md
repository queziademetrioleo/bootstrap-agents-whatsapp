# Deploy no GCP

Toda a infra é provisionada via **Terraform** (`infra/terraform/`). Um workspace
por ambiente (`dev`, `prod`). Esta é a ordem de execução do plano, do zero.

## Pré-requisitos

- `gcloud` autenticado com permissões de admin no projeto (ver tabela de roles
  do Terraform/Dev no plano).
- `terraform >= 1.6`, `docker`, `psql`.
- Um projeto GCP criado e billing habilitado.

```bash
gcloud config set project SEU_PROJECT_ID
gcloud auth application-default login
```

## 1. Provisionar a infra (Terraform)

```bash
cd infra/terraform
cp dev.tfvars.example dev.tfvars     # edite project_id, db_password, etc.

terraform init
terraform workspace new dev          # (ou: terraform workspace select dev)
terraform apply -var-file=dev.tfvars
```

Isso cria, na ordem de dependência: APIs habilitadas, VPC + connector + NAT, SAs
e IAM, Cloud SQL, Memorystore, Pub/Sub (+ DLQ), Artifact Registry, Secret Manager,
o Compute Engine da Evolution e os dois serviços do Cloud Run.

Guarde os outputs:

```bash
terraform output            # webhook_url, evolution_external_ip, db_connection_name, ...
terraform output -raw evolution_api_key
```

> **Nota:** o `apply` inicial pode levar ~15-20 min (Cloud SQL e service networking
> são os mais lentos). Os serviços do Cloud Run sobem com uma imagem placeholder na
> 1ª vez? Não — eles referenciam `agent:dev-latest`. Faça o **passo 3** (build) para
> publicar a imagem; se o apply reclamar que a imagem não existe, rode o build antes
> e depois `terraform apply` de novo, ou comente os recursos `cloud_run_v2` no 1º
> apply e descomente após o build.

## 2. Schema + extensão pgvector

O Terraform cria a instância e o banco, mas o schema é aplicado via SQL. Conecte
pelo Cloud SQL Auth Proxy (a instância não tem IP público):

```bash
# baixe o proxy: https://cloud.google.com/sql/docs/postgres/sql-proxy
./cloud-sql-proxy SEU_PROJECT_ID:southamerica-east1:agent-db-dev &

psql "postgresql://agent:SENHA@127.0.0.1:5432/agent" -f ../../scripts/init_db.sql
```

`init_db.sql` roda `CREATE EXTENSION vector;` + cria as 5 tabelas + o agente
`default`.

## 3. Build + deploy da aplicação (Cloud Build)

### Opção A — trigger automático

Se você setou `github_owner`/`github_repo` no tfvars, o trigger já existe:
push em `main` → deploy em **dev**; push em `release` → deploy em **prod**.

### Opção B — build manual

```bash
cd ../..   # raiz do repo
gcloud builds submit --config infra/cloudbuild.yaml \
  --substitutions=_ENV=dev,_REGION=southamerica-east1
```

Isso builda a imagem, publica no Artifact Registry e atualiza os dois serviços
do Cloud Run (webhook + processador) com a SA do agente anexada.

## 4. Ingerir a base de conhecimento

```bash
# com o cloud-sql-proxy ativo e USE_CLOUD_SQL=false apontando para 127.0.0.1
python scripts/ingest.py --csv knowledge/default.csv --agent-id default
```

## 5. Conectar a Evolution e o primeiro número

Siga `docs/creating-a-new-agent.md` (criar instância, parear QR, setar webhook
para o `webhook_url` do output).

## 6. Validar ponta a ponta

Mande uma mensagem ao número pareado e acompanhe:

```bash
gcloud run services logs read agent-processor-dev --region southamerica-east1
```

Você deve ver: `RAG retrieve` → (opcional `Tool executada`) → `Turno concluido`,
e a resposta chegando no WhatsApp.

## Produção

```bash
cp prod.tfvars.example prod.tfvars   # ajuste db_tier, etc.
terraform workspace new prod
terraform apply -var-file=prod.tfvars
gcloud builds submit --config infra/cloudbuild.yaml --substitutions=_ENV=prod
```

Diferenças automáticas em prod (ver `versions.tf`): `min-instances=1` (sem cold
start), Cloud SQL `REGIONAL` com backup + PITR e `deletion_protection`.

## Segurança — checklist

- [ ] **Webhook autenticado:** a Evolution envia o header `x-webhook-token` com o
      valor do output `webhook_token` (o app rejeita 401 sem ele). Ver
      `docs/creating-a-new-agent.md`.
- [ ] **Guardrails (Model Armor)** habilitados em prod (`model_armor_enabled=true`)
      — filtra prompt injection, jailbreak, conteúdo perigoso e URLs maliciosas.
- [ ] **`admin_cidrs`** restrito (NÃO `0.0.0.0/0`) — SSH via IAP, manager UI só do
      IP do time.
- [ ] Cloud SQL e Memorystore sem IP público (default do Terraform).
- [ ] Segredos (DB, Evolution, webhook, externos) só no Secret Manager; credenciais
      GCP (Vertex, SQL, Model Armor) via IAM.
- [ ] Push do Pub/Sub e Cloud Scheduler autenticados por OIDC + invoker IAM.
- [ ] PII (telefone) mascarada nos logs.

## Custo aproximado (volume baixo/médio)

Cloud SQL `db-f1-micro` ~$7/mês + Memorystore Basic 1GB ~$16/mês + Compute Engine
e2-micro ~$7/mês + Cloud Run/Pub/Sub/Vertex sob demanda (escala a zero em dev).
