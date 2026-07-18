"""Aplicação FastAPI para o Orquestrador de Moderação de Conteúdo."""

import logging
from typing import cast
import httpx

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite import SqliteSaver

# Importando o builder e o stream do serviço de moderação
from service import builder, executar_orquestrador_stream
from schemas import HumanInterventionRequest, ChatRequest

# Importações da AG-UI
from ag_ui.core import (
    RunAgentInput,
    EventType,
    RunStartedEvent,
    RunFinishedEvent,
    BaseEvent,
)
from ag_ui.encoder import EventEncoder

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
checkpointer = SqliteSaver.from_conn_string("moderation_checkpoints.db")

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
    config = {"configurable": {"thread_id": data.thread_id}}

    # Atualiza o estado do grafo no ponto de interrupção
    graph.update_state(
        config,
        {
            "decisao_final": data.nova_classificacao,
            "justificativa_agente": data.nova_justificativa or "Intervenção humana.",
        },
        as_node="revisao_humana",
    )

    # Resume a execução do grafo após o breakpoint
    # O valor None indica que estamos retomando o estado atual
    await graph.ainvoke(None, config)

    logger.info("Decisão humana aplicada na thread: %s", data.thread_id)
    return {"status": "success", "message": "Intervenção processada e fluxo concluído."}


@app.post("/")
async def moderation_endpoint(input_data: RunAgentInput, request: Request):
    """Endpoint SSE para a AG-UI executar a moderação."""
    accept_header = request.headers.get("accept") or "text/event-stream"
    encoder = EventEncoder(accept=accept_header)

    async def event_generator():
        try:
            # 1. Sinaliza início da execução na UI
            yield encoder.encode(
                cast(
                    BaseEvent,
                    RunStartedEvent(
                        type=EventType.RUN_STARTED,
                        thread_id=input_data.thread_id,
                        run_id=input_data.run_id,
                    ),
                )
            )

            # 2. Injeta o grafo compilado no fluxo de stream
            async for event in executar_orquestrador_stream(input_data, graph):
                yield encoder.encode(cast(BaseEvent, event))

            # 3. Sinaliza fim da execução
            yield encoder.encode(
                cast(
                    BaseEvent,
                    RunFinishedEvent(
                        type=EventType.RUN_FINISHED,
                        thread_id=input_data.thread_id,
                        run_id=input_data.run_id,
                    ),
                )
            )
        except Exception as e:
            logger.error("Erro no fluxo de moderação: %s", e, exc_info=True)
            yield encoder.encode(
                cast(
                    BaseEvent,
                    RunFinishedEvent(
                        type=EventType.RUN_FINISHED,
                        thread_id=input_data.thread_id,
                        run_id=input_data.run_id,
                    ),
                )
            )

    return StreamingResponse(event_generator(), media_type=encoder.get_content_type())
