"""Módulo Supervisor de Moderação – Orquestração A2A v1.0 e Estado Persistente."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator, Dict
import uuid

from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# Cliente A2A oficial (evita manipulação manual de JSON-RPC)
from a2a.client import A2AClient
from a2a.types import Message, Role, Part, SendMessageRequest, TextPart

# Schemas internos (ajuste o import conforme sua estrutura)
from schemas import ModerationState

logger = logging.getLogger("orchestrator.service")
load_dotenv()

# ============================================================================
# 1. CONFIGURAÇÃO DE PERSISTÊNCIA ASSÍNCRONA (SQLite MVP)
# ============================================================================
DB_PATH = "/app/shared_db/mvp_database.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# AsyncSqliteSaver já gerencia a conexão internamente via aiosqlite
checkpointer = AsyncSqliteSaver.from_conn_string(DB_PATH)

# URLs dos agentes (rede interna Docker)
ANALYST_URL = os.getenv("ANALYST_AGENT_URL", "http://analyst-agent:5001/rpc")
AUDITOR_URL = os.getenv("AUDITOR_AGENT_URL", "http://auditor-agent:5002/rpc")
MODERATOR_URL = os.getenv("MODERATOR_AGENT_URL", "http://moderator-agent:5003/rpc")

# ============================================================================
# 2. CLIENTES A2A PRÉ‑INSTANCIADOS (reutilizáveis)
# ============================================================================
analyst_client = A2AClient(ANALYST_URL)
auditor_client = A2AClient(AUDITOR_URL)
moderator_client = A2AClient(MODERATOR_URL)


# ============================================================================
# 3. NÓS DE EXECUÇÃO ASSÍNCRONOS (A2A v1.0 nativo)
# ============================================================================
async def node_analyst_agent(state: ModerationState) -> Dict[str, Any]:
    """Nó 1: Invoca o microsserviço Analyst para extrair propriedades cognitivas."""
    logger.info("[Grafo] Chamando Analyst Agent via A2A...")

    # Montagem correta da requisição A2A (SendMessageRequest)
    msg = Message(
        role=Role.ROLE_USER,
        parts=[TextPart(text=state.comentario_original)],
    )
    request = SendMessageRequest()
    request.message.CopyFrom(msg)

    response = await analyst_client.send_message(request)
    # Extrai o texto da resposta do agente
    if response.message.parts:
        raw_text = response.message.parts[0].text
    else:
        raw_text = "{}"
    data = json.loads(raw_text)

    return {
        "classificacao": data.get("classificacao", "neutro"),
        "analise_do_agente": data.get("analise_do_agente", ""),
    }


async def node_auditor_agent(state: ModerationState) -> Dict[str, Any]:
    """Nó 2: Aciona o Auditor para buscar diretrizes se o texto for problemático."""
    logger.info("[Grafo] Chamando Auditor Agent para avaliar violações...")

    msg = Message(
        role=Role.ROLE_USER,
        parts=[TextPart(text=state.analise_do_agente)],
    )
    request = SendMessageRequest()
    request.message.CopyFrom(msg)

    response = await auditor_client.send_message(request)
    raw_text = response.message.parts[0].text if response.message.parts else "{}"
    data = json.loads(raw_text)

    return {"politicas_relevantes": data.get("politicas_relevantes", [])}


async def node_moderator_agent(state: ModerationState) -> Dict[str, Any]:
    """Nó 3: Invoca o Moderador para cruzar os dados e gerar a recomendação final."""
    logger.info("[Grafo] Chamando Moderator Agent para consolidação do veredito...")

    input_consolidado = (
        f"Análise: {state.analise_do_agente} | "
        f"Políticas: {', '.join(state.politicas_relevantes)}"
    )
    msg = Message(
        role=Role.ROLE_USER,
        parts=[TextPart(text=input_consolidado)],
    )
    request = SendMessageRequest()
    request.message.CopyFrom(msg)

    response = await moderator_client.send_message(request)
    raw_text = response.message.parts[0].text if response.message.parts else "{}"
    data = json.loads(raw_text)

    return {
        "recomendacao_acao": data.get("recomendacao_acao"),
        "justificativa_moderacao": data.get("justificativa_moderacao"),
    }


async def node_human_gate(state: ModerationState) -> ModerationState:
    """Nó 4: Ponto de barreira rígida. Aguarda intervenção manual."""
    logger.info("[Grafo] Fluxo pausado no human_gate. Aguardando decisão do moderador.")
    return state


# ============================================================================
# 4. ROTEAMENTO CONDICIONAL E COMPILAÇÃO (LangGraph)
# ============================================================================
def verificar_necessidade_auditoria(state: ModerationState) -> str:
    """Roteador probabilístico avaliando o veredito do analista."""
    if state.classificacao == "potencialmente problemático":
        return "auditor-agent"
    return "moderator-agent"


workflow = StateGraph(ModerationState)

workflow.add_node("analyst-agent", node_analyst_agent)
workflow.add_node("auditor-agent", node_auditor_agent)
workflow.add_node("moderator-agent", node_moderator_agent)
workflow.add_node("human_gate", node_human_gate)

workflow.add_edge(START, "analyst-agent")
workflow.add_conditional_edges(
    "analyst-agent",
    verificar_necessidade_auditoria,
    {"auditor-agent": "auditor-agent", "moderator-agent": "moderator-agent"},
)
workflow.add_edge("auditor-agent", "moderator-agent")
workflow.add_edge("moderator-agent", "human_gate")
workflow.add_edge("human_gate", END)

# COMPILAÇÃO COM CHECKPOINTER ASSÍNCRONO
graph = workflow.compile(checkpointer=checkpointer, interrupt_before=["human_gate"])


# ============================================================================
# 5. GERENCIAMENTO DE CONTEXTO E STREAMING
# ============================================================================
async def preparar_contexto_moderacao(thread_id: str) -> Dict[str, Any]:
    """Busca o snapshot tratado no SQLite para o painel React."""
    config = {"configurable": {"thread_id": thread_id}}
    state_snapshot = await graph.aget_state(config)
    return state_snapshot.values if state_snapshot.values else {}


async def aplicar_intervencao_humana(thread_id: str, dados_humanos: Dict[str, Any]) -> None:
    """Grava as correções do humano no banco e destrava a execução até o END."""
    config = {"configurable": {"thread_id": thread_id}}

    await graph.aupdate_state(
        config,
        {
            "decisao_final_humano": dados_humanos.get("nova_classificacao"),
            "justificativa_humano": dados_humanos.get("nova_justificativa"),
            "comentario_final_aprovado": dados_humanos.get("comentario_editado"),
        },
        as_node="human_gate",
    )
    logger.info("[Grafo] Snapshot atualizado via HitL para thread %s", thread_id)

    # Destrava enviando None para o loop prosseguir do ponto de interrupção
    await graph.ainvoke(None, config)


async def executar_orquestrador_stream(
    data: ChatRequest,
) -> AsyncIterator[str]:
    """Gera eventos SSE simulando o processamento do pipeline."""
    config = {"configurable": {"thread_id": data.thread_id}}
    input_inicial = {"comentario_original": data.message, "thread_id": data.thread_id}

    async for event in graph.astream(input_inicial, config, stream_mode="updates"):
        for node_name, values in event.items():
            payload = {"node": node_name, "data": values}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
