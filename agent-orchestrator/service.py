"""Módulo de Orquestração do Grafo para o Sistema de Moderação."""

from __future__ import annotations

import json
import logging
import uuid
from types import SimpleNamespace
from typing import Annotated, AsyncGenerator, Dict, Any, TypedDict, Optional, Sequence, cast

import httpx
from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

from a2a.client import A2ACardResolver, create_client, ClientConfig
from a2a.types import Message, Part, Role, SendMessageRequest
from a2a.helpers import get_stream_response_text

# Eventos do AG-UI
from ag_ui.core import (
    EventType,
    TextMessageStartEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
)

logger = logging.getLogger("moderation.orchestrator")

HTTPX_CLIENT = httpx.AsyncClient(timeout=30)
CLIENT_CACHE: Dict[str, Any] = {}

# -----------------------------
# REGISTRY DE AGENTES / BFA
# -----------------------------
# Em um ambiente 100% dinâmico, o BFA entregaria essa URL.
# Para o orquestrador, já mapeamos a porta 5001 exposta no server.py do Analista.
AGENTS = {
    "analyst": "http://analyst-agent:5001",
}

# -----------------------------
# PRESERVAR CONTEXTO HISTÓRICO
# -----------------------------


def limit_messages(
    state: ModerationState, new_messages: Sequence[BaseMessage]
) -> list[BaseMessage]:
    """Reduz o histórico de mensagens para os últimos 10 itens."""
    current_messages = cast(list[BaseMessage], state.get("messages", []))
    messages = add_messages(current_messages, new_messages)
    return messages[-10:]


# -----------------------------
# STATE DO LANGGRAPH (MODERAÇÃO)
# -----------------------------
class ModerationState(TypedDict):
    """Estado persistente com gestão de histórico."""

    # add_messages aqui atua como o reducer.
    # Você pode configurar max_messages ou usar uma função customizada.
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # Seus campos de controle continuam aqui
    comentario_original: str
    classificacao: Optional[str]
    justificativa_agente: Optional[str]
    revisao_humana_necessaria: bool
    decisao_final: Optional[str]
    comentario_editado: Optional[str]
    justificativa_humana: Optional[str]


# -----------------------------
# EVENTO PARA STATE UPDATE NO AG-UI
# -----------------------------
class StateUpdateEvent(BaseModel):
    """Evento de atualização de estado enviado ao Frontend UI."""

    type: str = "STATE_UPDATE"
    state: dict


# -----------------------------
# CHAMADA PARA O AGENTE ANALISTA (A2A v1.0)
# -----------------------------
async def request_analyst_agent(message: str, agent_url: str) -> Dict[str, str]:
    """Chama o Analyst Agent e realiza o parse do output estruturado (JSON)."""
    if agent_url not in CLIENT_CACHE:
        logger.info("Descobrindo AgentCard em %s", agent_url)
        resolver = A2ACardResolver(httpx_client=HTTPX_CLIENT, base_url=agent_url)
        agent_card = await resolver.get_agent_card()
        config = ClientConfig(httpx_client=HTTPX_CLIENT, polling=False)
        CLIENT_CACHE[agent_url] = await create_client(agent_card, config)

    client = CLIENT_CACHE[agent_url]
    msg = Message(
        role=Role.ROLE_USER,
        message_id=str(uuid.uuid4()),
        parts=[Part(text=message)],
    )

    request = SendMessageRequest()
    request.message.CopyFrom(msg)

    texto_resposta = ""
    async for chunk in client.send_message(request):
        if chunk.HasField("message"):
            texto = get_stream_response_text(chunk)
            if texto:
                texto_resposta += texto

    # O agente Analista devolve um JSON na resposta de texto
    try:
        resultado = json.loads(texto_resposta)
        # Retorna o dicionário contendo "classificacao" e "analise_do_agente"
        return resultado.get("structured_response", {})
    except json.JSONDecodeError:
        logger.error("Falha ao decodificar JSON do agente: %s", texto_resposta)
        return {
            "classificacao": "neutro",
            "analise_do_agente": "Erro de parse. Fallback para neutro.",
        }


# -----------------------------
# NODES DO GRAFO
# -----------------------------
async def node_analise_inicial(state: ModerationState) -> Dict[str, Any]:
    """Node 1: Envia o comentário para o Analyst Agent classificar."""
    comentario = state["comentario_original"]
    logger.info("Enviando para análise semântica...")

    resultado = await request_analyst_agent(comentario, AGENTS["analyst"])

    classificacao = resultado.get("classificacao", "neutro")
    justificativa = resultado.get("analise_do_agente", "")

    precisa_revisao = classificacao == "potencialmente problemático"

    return {
        "classificacao": classificacao,
        "justificativa_agente": justificativa,
        "revisao_humana_necessaria": precisa_revisao,
    }


async def node_pesquisa_diretrizes(_state: ModerationState) -> Dict[str, Any]:
    """Node 2: Busca regras no Tavily (via BFA/MCP) se for problemático."""
    # Aqui implementaremos a chamada MCP para o Tavily no futuro
    # Por enquanto, preenchemos um placeholder
    logger.info("Pesquisando diretrizes de comunidade (Tavily/MCP)...")
    return {"diretrizes_violadas": "Regra 4: Linguagem inadequada (Simulação)"}


async def node_revisao_humana(state: ModerationState) -> Dict[str, Any]:
    """Node 3 (HitL): Ponto de parada. Se chegar aqui, o humano interveio."""
    logger.info("Retomando fluxo após intervenção do moderador.")
    resultado: Dict[str, Any] = {"decisao_final": state.get("decisao_final")}

    if state.get("comentario_editado"):
        resultado["comentario_final"] = state["comentario_editado"]

    if state.get("justificativa_humana"):
        resultado["justificativa_humana"] = state["justificativa_humana"]

    return resultado


# -----------------------------
# ROTEAMENTO CONDICIONAL
# -----------------------------
def roteamento_pos_analise(state: ModerationState) -> str:
    """Decide se o fluxo exige pesquisa de diretrizes e revisão humana."""
    if state.get("revisao_humana_necessaria"):
        return "pesquisa_diretrizes"
    return END


# -----------------------------
# BUILD DO GRAFO
# -----------------------------
builder = StateGraph(ModerationState)
builder.add_node("analise_inicial", node_analise_inicial)
builder.add_node("pesquisa_diretrizes", node_pesquisa_diretrizes)
builder.add_node("revisao_humana", node_revisao_humana)

builder.add_edge(START, "analise_inicial")
builder.add_conditional_edges("analise_inicial", roteamento_pos_analise)
builder.add_edge("pesquisa_diretrizes", "revisao_humana")
builder.add_edge("revisao_humana", END)

# O grafo não é compilado aqui, pois precisamos passar o checkpointer (SQLite)
# na inicialização da aplicação (geralmente no app.py)
# graph = builder.compile(checkpointer=memory)


# -----------------------------
# STREAMING DO ORQUESTRADOR (AG-UI)
# -----------------------------
def _serialize_event(event: Any) -> str:
    if hasattr(event, "model_dump"):
        payload = event.model_dump()
    elif hasattr(event, "dict"):
        payload = event.dict()
    else:
        payload = event.__dict__
    serialized = json.dumps(payload)
    serialized = serialized.replace("\n", "\ndata: ")
    return f"data: {serialized}\n\n"


async def executar_orquestrador_stream(
    input_data: Any,
    graph_runnable,
) -> AsyncGenerator[str, None]:
    """Executa o grafo e converte a progressão em eventos visuais no AG-UI."""
    if hasattr(input_data, "messages"):
        messages = input_data.messages
    elif hasattr(input_data, "message"):
        messages = [SimpleNamespace(content=getattr(input_data, "message"))]
    else:
        messages = []

    comentario = messages[-1].content if messages else ""
    thread_id = getattr(input_data, "thread_id", str(uuid.uuid4()))
    assistant_id = str(uuid.uuid4())

    yield _serialize_event(
        TextMessageStartEvent(
            type=EventType.TEXT_MESSAGE_START,
            message_id=assistant_id,
            role="assistant",
        )
    )

    yield _serialize_event(
        TextMessageContentEvent(
            type=EventType.TEXT_MESSAGE_CONTENT,
            message_id=assistant_id,
            delta="Iniciando triagem do comentário...\n\n",
        )
    )

    config = {"configurable": {"thread_id": thread_id}}

    # Executa o grafo com stream_mode="updates" para ver a saída de cada Node
    async for output in graph_runnable.astream(
        {"comentario_original": comentario}, config=config, stream_mode="updates"
    ):
        if "analise_inicial" in output:
            dados = output["analise_inicial"]
            delta = (
                f"**Classificação:** {dados['classificacao'].upper()}\n"
                f"**Justificativa:** {dados['justificativa_agente']}\n\n"
            )
            yield _serialize_event(
                TextMessageContentEvent(
                    type=EventType.TEXT_MESSAGE_CONTENT,
                    message_id=assistant_id,
                    delta=delta,
                )
            )

            if dados["revisao_humana_necessaria"]:
                yield _serialize_event(
                    TextMessageContentEvent(
                        type=EventType.TEXT_MESSAGE_CONTENT,
                        message_id=assistant_id,
                        delta=(
                            "⚠️ *Atenção: Comentário retido para revisão do moderador.* "
                            "Aguardando ação.\n"
                        ),
                    )
                )

        if "pesquisa_diretrizes" in output:
            regras = output["pesquisa_diretrizes"]["diretrizes_violadas"]
            yield _serialize_event(
                TextMessageContentEvent(
                    type=EventType.TEXT_MESSAGE_CONTENT,
                    message_id=assistant_id,
                    delta=f"**Diretrizes Mapeadas (Tavily):** {regras}\n\n",
                )
            )

        yield _serialize_event(StateUpdateEvent(state=output))

    yield _serialize_event(
        TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id=assistant_id)
    )
