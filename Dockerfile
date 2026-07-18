FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia a estrutura mínima para validação do Setuptools
COPY pyproject.toml README.md ./

# Cria uma pasta mock vazia para o setuptools não falhar na autodescoberta antes de copiar tudo
RUN mkdir -p agent-orchestrator agents bfa_service

# Instala todas as dependências de uma única vez (Orquestrador, BFA e Agentes)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[orchestrator,bfa_service,agent_analyst,agent_auditor,agent_moderator]"

# Copia o restante do código-fonte
COPY . .

# Não precisamos de um CMD fixo aqui, pois o docker-compose cuidará disso para cada container
