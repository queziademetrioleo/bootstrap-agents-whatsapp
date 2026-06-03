#!/usr/bin/env bash
# Startup script da VM da Evolution API (passo 4).
# Instala Docker + Compose e sobe a Evolution com Redis/Postgres internos
# (exclusivos dela). O .env e montado a partir de metadados da instancia.
#
# Importante (issue #1474): a imagem ignora variaveis passadas via `environment:`.
# Por isso usamos SEMPRE `env_file: .env` e garantimos o .env presente na raiz.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl gnupg

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

mkdir -p /opt/evolution
cd /opt/evolution

# Le valores dos metadados da instancia.
API_KEY="$(curl -s -H 'Metadata-Flavor: Google' 'http://metadata.google.internal/computeMetadata/v1/instance/attributes/evolution-api-key')"

# O webhook NAO e definido aqui (seria um ciclo com o Cloud Run). Configure-o
# por instancia, apos o deploy, via API: POST /webhook/set/{instance} com a URL
# do Cloud Run e o header x-webhook-token (ver docs/creating-a-new-agent.md).
cat > .env <<EOF
SERVER_URL=http://0.0.0.0:8080
AUTHENTICATION_TYPE=apikey
AUTHENTICATION_API_KEY=${API_KEY}

DATABASE_PROVIDER=postgresql
DATABASE_CONNECTION_URI=postgresql://evolution:evolution@evolution_postgres:5432/evolution
DATABASE_ENABLED=true

CACHE_REDIS_ENABLED=true
CACHE_REDIS_URI=redis://evolution_redis:6379
EOF

cat > docker-compose.yaml <<'EOF'
services:
  evolution_api:
    image: evoapicloud/evolution-api:latest
    restart: always
    ports:
      - "8080:8080"
    env_file: .env        # NUNCA usar bloco environment: (issue #1474)
    depends_on:
      - evolution_postgres
      - evolution_redis
    volumes:
      - evolution_instances:/evolution/instances

  evolution_postgres:
    image: postgres:15
    restart: always
    environment:
      POSTGRES_USER: evolution
      POSTGRES_PASSWORD: evolution
      POSTGRES_DB: evolution
    volumes:
      - evolution_pg:/var/lib/postgresql/data

  evolution_redis:
    image: redis:7
    restart: always
    volumes:
      - evolution_redis:/data

volumes:
  evolution_instances:
  evolution_pg:
  evolution_redis:
EOF

docker compose up -d
