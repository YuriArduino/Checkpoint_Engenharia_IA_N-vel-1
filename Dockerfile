FROM python:3.13-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia os arquivos de configuração centrais para a raiz do container
COPY pyproject.toml README.md ./

# Instala as dependências base do projeto
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Recebe o nome do serviço vindo do docker-compose e instala apenas o extra necessário + dependências comuns
ARG BUILD_ENV
RUN if [ ! -z "$BUILD_ENV" ]; then pip install --no-cache-dir ".[$BUILD_ENV]"; fi

# Copia todo o código-fonte respeitando a nova estrutura (agents, bfa_service, agent-orchestrator)
COPY . .
