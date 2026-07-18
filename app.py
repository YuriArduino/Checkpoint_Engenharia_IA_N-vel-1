"""Aplicação FastAPI para o Orquestrador de Moderação de Conteúdo."""

import importlib
import logging
import os
import sqlite3
import sys
from typing import cast

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver

# Torna o pacote agent-orchestrator importável a partir da raiz do projeto
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
logger = logging.getLogger("moderation.app")

app = FastAPI(title="Moderation Orchestrator AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Configuração de Persistência SQLite
# Criamos o banco de checkpoints especificamente para o fluxo de moderação
connection = sqlite3.connect("moderation_checkpoints.db", check_same_thread=False)
checkpointer = SqliteSaver(connection)

# 2. Compilação do Grafo com Interrupção (HitL)
# O grafo pausa antes de executar o nó 'revisao_humana', esperando ação humana.
graph = builder.compile(checkpointer=checkpointer, interrupt_before=["revisao_humana"])


@app.post("/human-decision")
async def human_decision(data: HumanInterventionRequest):
    """
    Endpoint de Intervenção Humana (HitL).
    1. Atualiza o estado persistido com a decisão do moderador.
    2. Resume o fluxo do grafo.
    """
    config = cast(RunnableConfig, {"configurable": {"thread_id": data.thread_id}})

    # Atualiza o estado do grafo no ponto de interrupção
    payload = {"decisao_final": data.nova_classificacao}
    if data.nova_justificativa:
        payload["justificativa_humana"] = data.nova_justificativa
    if data.comentario_editado:
        payload["comentario_editado"] = data.comentario_editado

    graph.update_state(
        config,
        payload,
        as_node="revisao_humana",
    )

    # Resume a execução do grafo após o breakpoint
    # O valor None indica que estamos retomando o estado atual
    await graph.ainvoke(None, config)

    logger.info("Decisão humana aplicada na thread: %s", data.thread_id)
    return {"status": "success", "message": "Intervenção processada e fluxo concluído."}


@app.post("/")
async def moderation_endpoint(input_data: ChatRequest):
    """Endpoint SSE para executar a moderação de comentários."""

    async def event_generator():
        async for event in executar_orquestrador_stream(input_data, graph):
            yield event

    return StreamingResponse(event_generator(), media_type="text/event-stream")
