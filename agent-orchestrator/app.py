"""Módulo Principal (FastAPI) - Orquestrador de Moderação."""

import logging
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

# Importa o builder e o stream do serviço
from service import builder, executar_orquestrador_stream
from schemas import HumanInterventionRequest, ChatRequest

logger = logging.getLogger("moderation.app")

# 1. Persistência SQLite
connection = sqlite3.connect("moderation_checkpoints.db", check_same_thread=False)
checkpointer = SqliteSaver(connection)

# 2. Compilação com Breakpoint
# O grafo irá PAUSAR antes de executar o nó de revisão humana.
graph = builder.compile(checkpointer=checkpointer, interrupt_before=["revisao_humana"])

app = FastAPI(title="Orquestrador de Moderação AI")


@app.post("/stream")
async def stream_moderation(request: ChatRequest):
    """Endpoint para iniciar a análise do comentário."""
    return StreamingResponse(
        executar_orquestrador_stream(request, graph), media_type="text/event-stream"
    )


@app.post("/human-decision")
async def human_decision(data: HumanInterventionRequest):
    """
    Endpoint de Human-in-the-Loop.
    1. Atualiza o estado com a decisão final do moderador.
    2. Resume o grafo após o breakpoint.
    """
    config = {"configurable": {"thread_id": data.thread_id}}

    # Atualiza o estado com a decisão humana e com as intervenções extras do moderador
    payload = {"decisao_final": data.nova_classificacao}
    if data.nova_justificativa:
        payload["justificativa_humana"] = data.nova_justificativa
    if data.comentario_editado:
        payload["comentario_editado"] = data.comentario_editado

    graph.update_state(config, payload, as_node="revisao_humana")

    # Resume a execução do grafo a partir do ponto de interrupção
    # Passamos None para indicar que queremos continuar o fluxo atual
    await graph.ainvoke(None, config)

    return {"status": "success", "message": "Intervenção processada e fluxo concluído."}
