"""Aplicação FastAPI do Agent Orchestrator de moderação."""

from contextlib import asynccontextmanager
import logging
import os
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# Importação dos schemas estruturados do frontend
from schemas import ChatRequest, HumanInterventionRequest

# CORREGIDO: Importa a inteligência e os wrappers do módulo real service.py
from service import (
    builder,
    executar_orquestrador_stream,
    aplicar_intervencao_humana,
    preparar_contexto_moderacao,
)

logger = logging.getLogger("orchestrator.app")


@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
    """Injeta o grafo pré-compilado (builder) no estado global da API."""
    logger.info("[Orchestrator] Inicializando Gateway de Orquestração...")

    # Acopla a esteira linear configurada com a persistência do SQLite do MVP
    app_instance.state.graph = builder
    yield
    logger.info("[Orchestrator] Encerrando Gateway de Orquestração.")


app = FastAPI(title="Orquestrador de Moderação AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check do orquestrador para monitoramento do Docker Compose."""
    return {"status": "ok", "service": "agent_orchestrator"}


@app.post("/stream")
async def stream_moderation(request: Request, data: ChatRequest) -> StreamingResponse:
    """Inicia a análise do comentário e emite eventos SSE compatíveis com AG-UI."""
    logger.info("[API] Nova requisição de comentário para thread: %s", data.thread_id)

    return StreamingResponse(
        executar_orquestrador_stream(data, request.app.state.graph),
        media_type="text/event-stream",
    )


@app.get("/thread/{thread_id}")
async def obter_estado_thread(thread_id: str) -> dict[str, Any]:
    """Retorna o snapshot completo de variáveis do SQLite para o painel React."""
    snapshot = await preparar_contexto_moderacao(thread_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Thread não localizada na base do MVP.")
    return snapshot


@app.post("/human-decision")
async def human_decision(data: HumanInterventionRequest) -> dict[str, str]:
    """Atualiza a decisão humana no checkpoint e resume o grafo pausado."""
    logger.info("[API] Intervenção manual recebida para thread: %s", data.thread_id)

    payload_humano = {
        "nova_classificacao": data.nova_classificacao,
        "nova_justificativa": data.nova_justificativa,
        "comentario_editado": data.comentario_editado,
    }

    try:
        # Aciona o gerenciador do service que atualiza o SQLite e roda o fluxo até o END
        await aplicar_intervencao_humana(data.thread_id, payload_humano)
        return {"status": "success", "message": "Intervenção processada e fluxo concluído."}
    except Exception as e:
        logger.error("[API] Falha ao processar liberação da barreira humana: %s", e)
        raise HTTPException(status_code=500, detail="Erro interno ao destravar o fluxo.")
