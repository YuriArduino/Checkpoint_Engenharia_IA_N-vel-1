"""Aplicação FastAPI do Agent Orchestrator de moderação."""

from contextlib import asynccontextmanager
import logging
import os
from typing import Any, AsyncIterator, cast

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from schemas import ChatRequest, HumanInterventionRequest
from service import builder, executar_orquestrador_stream

logger = logging.getLogger("moderation.app")

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


app = FastAPI(title="Orquestrador de Moderação AI", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _build_human_payload(data: HumanInterventionRequest) -> dict[str, Any]:
    """Monta somente os campos que o moderador alterou no estado."""
    payload: dict[str, Any] = {"decisao_final": data.nova_classificacao}
    if data.nova_justificativa:
        payload["justificativa_humana"] = data.nova_justificativa
    if data.comentario_editado:
        payload["comentario_editado"] = data.comentario_editado
    return payload


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check do orquestrador."""
    return {"status": "ok"}


@app.post("/")
@app.post("/stream")
async def stream_moderation(request: Request, data: ChatRequest) -> StreamingResponse:
    """Inicia a análise do comentário e emite eventos SSE compatíveis com AG-UI."""
    return StreamingResponse(
        executar_orquestrador_stream(data, request.app.state.graph),
        media_type="text/event-stream",
    )


@app.post("/human-decision")
async def human_decision(request: Request, data: HumanInterventionRequest) -> dict[str, str]:
    """Atualiza a decisão humana no checkpoint e resume o grafo pausado."""
    config = cast(RunnableConfig, {"configurable": {"thread_id": data.thread_id}})
    await request.app.state.graph.aupdate_state(
        config,
        _build_human_payload(data),
        as_node="revisao_humana",
    )
    await request.app.state.graph.ainvoke(None, config)

    logger.info("Decisão humana aplicada na thread: %s", data.thread_id)
    return {"status": "success", "message": "Intervenção processada e fluxo concluído."}
