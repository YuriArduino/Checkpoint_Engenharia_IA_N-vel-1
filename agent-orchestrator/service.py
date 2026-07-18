"""Módulo de orquestração do grafo para o sistema de moderação."""

from __future__ import annotations

import json
import logging
import os
import uuid
from types import SimpleNamespace
from typing import (
    Annotated,
    Any,
    AsyncGenerator,
    NotRequired,
    Optional,
    Required,
    Sequence,
    TypedDict,
)

import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_stream_response_text
from a2a.types import Message, Part, Role, SendMessageRequest
from ag_ui.core import (
    EventType,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from langchain_core.messages import BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel

logger = logging.getLogger("moderation.orchestrator")

HTTPX_CLIENT = httpx.AsyncClient(timeout=30)
CLIENT_CACHE: dict[str, Any] = {}

AGENTS = {
    "analyst": os.getenv("ANALYST_AGENT_URL", "http://analyst-agent:5001"),
}


class ModerationState(TypedDict):
    """Estado persistente do fluxo de moderação no LangGraph."""

    messages: NotRequired[Annotated[Sequence[BaseMessage], add_messages]]
    comentario_original: Required[str]
    classificacao: NotRequired[Optional[str]]
    justificativa_agente: NotRequired[Optional[str]]
    revisao_humana_necessaria: NotRequired[bool]
    diretrizes_violadas: NotRequired[Optional[str]]
    decisao_final: NotRequired[Optional[str]]
    comentario_editado: NotRequired[Optional[str]]
    comentario_final: NotRequired[Optional[str]]
    justificativa_humana: NotRequired[Optional[str]]


class StateUpdateEvent(BaseModel):
    """Evento de atualização de estado enviado ao frontend AG-UI."""

    type: str = "STATE_UPDATE"
    state: dict[str, Any]


def limit_messages(
    state: ModerationState, new_messages: Sequence[BaseMessage]
) -> list[BaseMessage]:
    """Reduz o histórico de mensagens para os últimos 10 itens."""
    current_messages = list(state.get("messages", ()))
    merged_messages = [*current_messages, *new_messages]
    return merged_messages[-10:]


def _normalizar_classificacao(classificacao: str) -> str:
    """Normaliza variações de classificação usadas pelos agentes especialistas."""
    normalized = classificacao.strip().lower().replace("_", " ")
    if normalized in {"problematico", "problemático", "potencialmente problemático"}:
        return "potencialmente problemático"
    if normalized in {"positivo", "neutro"}:
        return normalized
    return "neutro"


def _extrair_structured_response(texto_resposta: str) -> dict[str, str]:
    """Extrai a resposta estruturada do envelope A2A retornado pelo agente."""
    try:
        resultado = json.loads(texto_resposta)
    except json.JSONDecodeError:
        logger.error("Falha ao decodificar JSON do agente: %s", texto_resposta)
        return {
            "classificacao": "neutro",
            "analise_do_agente": "Erro de parse. Fallback para neutro.",
        }

    if isinstance(resultado, dict) and isinstance(resultado.get("structured_response"), dict):
        resultado = resultado["structured_response"]

    if not isinstance(resultado, dict):
        return {
            "classificacao": "neutro",
            "analise_do_agente": "Resposta do agente não veio em formato de objeto.",
        }

    return {
        "classificacao": str(resultado.get("classificacao", "neutro")),
        "analise_do_agente": str(resultado.get("analise_do_agente", "")),
    }


async def request_analyst_agent(message: str, agent_url: str) -> dict[str, str]:
    """Chama o Analyst Agent via A2A e parseia seu output estruturado."""
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

    return _extrair_structured_response(texto_resposta)


async def node_analise_inicial(state: ModerationState) -> dict[str, Any]:
    """Envia o comentário para o Analyst Agent classificar."""
    comentario = state["comentario_original"]
    logger.info("Enviando comentário para análise semântica.")

    resultado = await request_analyst_agent(comentario, AGENTS["analyst"])
    classificacao = _normalizar_classificacao(resultado.get("classificacao", "neutro"))

    return {
        "classificacao": classificacao,
        "justificativa_agente": resultado.get("analise_do_agente", ""),
        "revisao_humana_necessaria": classificacao == "potencialmente problemático",
    }


async def node_pesquisa_diretrizes(state: ModerationState) -> dict[str, Any]:
    """Busca regras no Tavily via BFA/MCP quando o comentário exigir revisão."""
    _ = state
    logger.info("Pesquisando diretrizes de comunidade via Tavily/MCP.")
    return {"diretrizes_violadas": "Regra 4: Linguagem inadequada (simulação)."}


async def node_revisao_humana(state: ModerationState) -> dict[str, Any]:
    """Ponto de retomada após intervenção do moderador humano."""
    logger.info("Retomando fluxo após intervenção do moderador.")
    resultado: dict[str, Any] = {"decisao_final": state.get("decisao_final")}

    if state.get("comentario_editado"):
        resultado["comentario_final"] = state.get("comentario_editado")

    if state.get("justificativa_humana"):
        resultado["justificativa_humana"] = state.get("justificativa_humana")

    return resultado


def roteamento_pos_analise(state: ModerationState) -> str:
    """Decide se o fluxo exige pesquisa de diretrizes e revisão humana."""
    if state.get("revisao_humana_necessaria"):
        return "pesquisa_diretrizes"
    return END


builder = StateGraph(ModerationState)
builder.add_node("analise_inicial", node_analise_inicial)
builder.add_node("pesquisa_diretrizes", node_pesquisa_diretrizes)
builder.add_node("revisao_humana", node_revisao_humana)

builder.add_edge(START, "analise_inicial")
builder.add_conditional_edges("analise_inicial", roteamento_pos_analise)
builder.add_edge("pesquisa_diretrizes", "revisao_humana")
builder.add_edge("revisao_humana", END)


def _serialize_event(event: Any) -> str:
    """Serializa eventos AG-UI no formato SSE."""
    if hasattr(event, "model_dump"):
        payload = event.model_dump()
    elif hasattr(event, "dict"):
        payload = event.dict()
    else:
        payload = event.__dict__

    serialized = json.dumps(payload, ensure_ascii=False).replace("\n", "\ndata: ")
    return f"data: {serialized}\n\n"


async def executar_orquestrador_stream(
    input_data: Any, graph_runnable: Any
) -> AsyncGenerator[str, None]:
    """Executa o grafo e converte a progressão em eventos visuais AG-UI."""
    if hasattr(input_data, "messages"):
        messages = input_data.messages
    elif hasattr(input_data, "message"):
        messages = [SimpleNamespace(content=getattr(input_data, "message"))]
    else:
        messages = []

    comentario = messages[-1].content if messages else ""
    thread_id = getattr(input_data, "thread_id", None) or str(uuid.uuid4())
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
    initial_state = {
        "comentario_original": comentario,
        "revisao_humana_necessaria": False,
        "decisao_final": None,
    }

    async for output in graph_runnable.astream(initial_state, config=config, stream_mode="updates"):
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
                            "⚠️ *Comentário retido para revisão do moderador.* "
                            "Aguardando ação humana.\n"
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
