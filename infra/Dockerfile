# Imagem unica para os dois servicos do Cloud Run (webhook receiver + processador).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencias primeiro (cache de camada).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Codigo. Inclui agent/ (core), tools/, integrations/ (auto-discovery em runtime).
COPY agent/ ./agent/
COPY tools/ ./tools/
COPY integrations/ ./integrations/

# Cloud Run injeta PORT. uvicorn escuta nela.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn agent.app:app --host 0.0.0.0 --port ${PORT}"]
