# Checkpoint: Sistema Inteligente de Moderação de Comentários (Engenharia de IA - Nível 1)

## 📌 Visão Geral da Arquitetura

Este projeto implementa um fluxo de trabalho avançado multiagente para moderação escalável de comentários em plataformas de cursos online. A arquitetura é totalmente descentralizada em microsserviços usando containers Docker isolados e comunicação baseada em protocolos modernos.

### Componentes do Ecossistema:

1. **Frontend (React + ag-ui):** Painel interativo para acompanhamento do fluxo e intervenção do moderador humano (_Human-in-the-Loop_).
2. **Supervisor Agent (LangGraph):** Orquestrador principal do grafo de estados. Gerencia os pontos de parada (_checkpoints_) para edição humana e aprovação final.
3. **Analyst Agent:** Agente especializado na análise semântica e comportamental do comentário.
4. **BFA (Broker & Finder Architecture):** Serviço de descoberta dinâmica que usa busca híbrida (FAISS para embeddings densos + BM25 para termos exatos) para rotear e encontrar agentes e ferramentas disponíveis.
5. **MCP Server (Tavily):** Servidor rodando Model Context Protocol para fornecer busca em tempo real de diretrizes externas.

## 🛠️ Como Executar o Projeto

### Pré-requisitos

- Docker & Docker Compose
- VS Code (recomendado abrir via `checkpoint-ia.code-workspace`)

### Inicialização Rápida

1. Clone o repositório
2. Copie o arquivo de ambientes: `cp .env.example .env` e preencha suas chaves de API.
3. Para testar somente backend/agentes, sem frontend:
   ```bash
   docker compose build
   docker compose up bfa-service agent-orchestrator analyst-agent auditor-agent moderator-agent
   ```
4. Para subir também o frontend React/ag-ui, use o profile `frontend`:
   ```bash
   docker compose --profile frontend up --build
   ```

### Teste rápido sem frontend

Com os containers de backend em execução, valide pelo terminal ou Insomnia:

```bash
curl http://localhost:8080/health
```

Para abrir o stream SSE do orquestrador:

```bash
curl -N -X POST http://localhost:8080/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"Este curso é ótimo, obrigado!","thread_id":"teste-local-1"}'
```

## 🧠 Fluxo de Estado e Intervenção Humana (Human-in-the-Loop)

O Grafo do LangGraph utiliza interrupções dinâmicas (`interrupt_before` ou `interrupt_after`) no nó de decisão do Moderador Humano. Isso congela o estado da thread, permitindo que a interface `ag-ui` consuma o estado via SSE (Server-Sent Events), apresente ao usuário a opção de editar a decisão do agente e atualize o estado diretamente antes de resumir o fluxo.
