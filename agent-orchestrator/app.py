"""Aplicação FastAPI do Agent Orchestrator de moderação."""

import logging
import os
import sqlite3
from typing import Any, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver

from schemas import ChatRequest, HumanInterventionRequest
from service import builder, executar_orquestrador_stream

logger = logging.getLogger("moderation.app")

DB_PATH = os.getenv("MODERATION_CHECKPOINT_DB", "moderation_checkpoints.db")
connection = sqlite3.connect(DB_PATH, check_same_thread=False)
checkpointer = SqliteSaver(connection)
graph = builder.compile(checkpointer=checkpointer, interrupt_before=["revisao_humana"])

app = FastAPI(title="Orquestrador de Moderação AI")
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
async def stream_moderation(request: ChatRequest) -> StreamingResponse:
    """Inicia a análise do comentário e emite eventos SSE compatíveis com AG-UI."""
    return StreamingResponse(
        executar_orquestrador_stream(request, graph),
        media_type="text/event-stream",
    )


@app.post("/human-decision")
async def human_decision(data: HumanInterventionRequest) -> dict[str, str]:
    """Atualiza a decisão humana no checkpoint e resume o grafo pausado."""
    config = cast(RunnableConfig, {"configurable": {"thread_id": data.thread_id}})
    graph.update_state(config, _build_human_payload(data), as_node="revisao_humana")
    await graph.ainvoke(None, config)

    logger.info("Decisão humana aplicada na thread: %s", data.thread_id)
    return {"status": "success", "message": "Intervenção processada e fluxo concluído."}
