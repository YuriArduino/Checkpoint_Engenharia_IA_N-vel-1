"""Aplicação FastAPI raiz para testar o orquestrador sem depender do frontend."""

from contextlib import asynccontextmanager
import importlib
import logging
import os
import sys
from typing import Any, AsyncIterator, cast

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

ROOT_DIR = os.path.dirname(__file__)
AG_ORCHESTRATOR_DIR = os.path.join(ROOT_DIR, "agent-orchestrator")
if AG_ORCHESTRATOR_DIR not in sys.path:
    sys.path.insert(0, AG_ORCHESTRATOR_DIR)

_service = importlib.import_module("service")
_schemas = importlib.import_module("schemas")

builder = _service.builder
executar_orquestrador_stream = _service.executar_orquestrador_stream
HumanInterventionRequest = _schemas.HumanInterventionRequest
ChatRequest = _schemas.ChatRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("moderation.root_app")

DB_PATH = os.getenv("MODERATION_CHECKPOINT_DB", "moderation_checkpoints.db")


@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
    """Mantém o checkpointer assíncrono aberto durante o ciclo de vida da API."""
    async with AsyncSqliteSaver.from_conn_string(DB_PATH) as checkpointer:
        app_instance.state.graph = builder.compile(
            checkpointer=checkpointer,
            interrupt_before=["revisao_humana"],
        )
        yield


app = FastAPI(title="Moderation Orchestrator AI", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _build_human_payload(data: HumanInterventionRequest) -> dict[str, Any]:
    """Monta somente os campos editáveis enviados pelo moderador humano."""
    payload: dict[str, Any] = {"decisao_final": data.nova_classificacao}
    if data.nova_justificativa:
        payload["justificativa_humana"] = data.nova_justificativa
    if data.comentario_editado:
        payload["comentario_editado"] = data.comentario_editado
    return payload


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check simples para Docker Compose e testes locais."""
    return {"status": "ok"}


@app.post("/human-decision")
async def human_decision(request: Request, data: HumanInterventionRequest) -> dict[str, str]:
    """Atualiza o estado com a decisão humana e resume o grafo pausado."""
    config = cast(RunnableConfig, {"configurable": {"thread_id": data.thread_id}})
    await request.app.state.graph.aupdate_state(
        config,
        _build_human_payload(data),
        as_node="revisao_humana",
    )
    await request.app.state.graph.ainvoke(None, config)

    logger.info("Decisão humana aplicada na thread: %s", data.thread_id)
    return {"status": "success", "message": "Intervenção processada e fluxo concluído."}


@app.post("/")
@app.post("/stream")
async def moderation_endpoint(request: Request, data: ChatRequest) -> StreamingResponse:
    """Endpoint SSE para executar a moderação de comentários sem frontend."""
    return StreamingResponse(
        executar_orquestrador_stream(data, request.app.state.graph),
        media_type="text/event-stream",
    )
