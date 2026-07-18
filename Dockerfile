FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

# Copia a estrutura mínima para validação do Setuptools
COPY pyproject.toml README.md ./

# Cria uma pasta mock vazia para o setuptools não falhar na autodescoberta antes de copiar tudo
RUN mkdir -p agent-orchestrator agents bfa_service

# Instala as dependências base do projeto
RUN pip install --no-cache-dir -e .

# Copia o restante do código-fonte
COPY . .

# Recebe o ambiente e instala o extra condicionalmente (Corrigido a sintaxe do IF)
ARG BUILD_ENV
RUN if [ -n "$BUILD_ENV" ]; then pip install --no-cache-dir ".[$BUILD_ENV]"; fi
