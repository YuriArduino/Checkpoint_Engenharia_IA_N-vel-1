"""Aplicação FastAPI raiz para testar o orquestrador de forma global."""

from contextlib import asynccontextmanager
import logging
import os
import sys
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# 1. Ajusta o sys.path para o Python mapear a pasta interna do orquestrador
ROOT_DIR = os.path.dirname(__file__)
AG_ORCHESTRATOR_DIR = os.path.join(ROOT_DIR, "agent-orchestrator")
if AG_ORCHESTRATOR_DIR not in sys.path:
    sys.path.insert(0, AG_ORCHESTRATOR_DIR)

# 2. Imports absolutos limpos (Agora que o sys.path conhece a pasta de dentro)
from schemas import ChatRequest, HumanInterventionRequest
from service import (
    builder,
    executar_orquestrador_stream,
    aplicar_intervencao_humana,
    preparar_contexto_moderacao,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("moderation.root_app")


@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
    """Injeta o grafo pré-compilado (builder) no estado global da API de teste."""
    logger.info("[Root App] Inicializando Gateway de Testes Local...")
    app_instance.state.graph = builder
    yield
    logger.info("[Root App] Encerrando Gateway de Testes.")


app = FastAPI(title="Moderation Orchestrator AI (Root Test Environment)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": "root_test"}


@app.post("/")
@app.post("/stream")
async def moderation_endpoint(request: Request, data: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        executar_orquestrador_stream(data, request.app.state.graph),
        media_type="text/event-stream",
    )


@app.get("/thread/{thread_id}")
async def obter_estado_thread_test(thread_id: str) -> dict[str, Any]:
    snapshot = await preparar_contexto_moderacao(thread_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Thread não localizada.")
    return snapshot


@app.post("/human-decision")
async def human_decision(data: HumanInterventionRequest) -> dict[str, str]:
    payload_humano = {
        "nova_classificacao": data.nova_classificacao,
        "nova_justificativa": data.nova_justificativa,
        "comentario_editado": data.comentario_editado,
    }
    try:
        await aplicar_intervencao_humana(data.thread_id, payload_humano)
        return {"status": "success", "message": "Intervenção processada com sucesso."}
    except Exception as e:
        logger.error("[Root App] Falha ao liberar barreira: %s", e)
        raise HTTPException(status_code=500, detail=f"Erro interno ao destravar o fluxo: {e}")
