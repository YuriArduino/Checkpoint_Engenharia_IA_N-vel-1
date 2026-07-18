"""Aplicação FastAPI principal para o ecossistema do BFA Service Hub."""

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Query
from mcp.server.fastmcp import FastMCP

from .database import init_db
from .registry import AGENT_REGISTRY, build_index, resolve_agent

logger = logging.getLogger("bfa.app")

bfa_mcp = FastMCP(
    name="BFA Service Gateway",
    instructions="Barramento MCP do BFA Service Hub para descoberta "
    "de ferramentas e consultas de diretrizes.",
    streamable_http_path="/",  # ← responde na raiz do subpath
)


@bfa_mcp.tool(
    name="bfa_resolve_tool",
    title="BFA Resolve Tool",
    description="Resolve uma consulta de regras ou agente no catálogo do BFA Service Hub.",
    structured_output=False,
)
async def bfa_resolve_tool(query: str) -> dict[str, Any]:
    """Resolve uma busca direta usando o catálogo híbrido de agentes e ferramentas."""
    result = await resolve_agent(query, top_k=3, k_rrf=60)
    if not result:
        return {"error": "no_confident_match", "best": None, "candidates": []}
    return result


# Obtém a aplicação ASGI do streamable HTTP
mcp_app = bfa_mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Gerenciador de ciclo de vida assíncrono para o BFA e o servidor MCP."""
    # Inicia o lifespan do MCP (task group, sessões, etc.) dentro do contexto do FastAPI
    async with mcp_app.router.lifespan_context(_app):
        logger.info("[BFA] Inicializando subsistemas do barramento central...")

        # 1. Garante a inicialização da tabela estruturada no SQLite compartilhado
        init_db()

        # 2. Executa a varredura de rede, ingestão no banco e compilação FAISS + BM25 RRF
        try:
            await build_index()
            logger.info("[BFA] Catálogo de habilidades e índices gerados com sucesso.")
        except Exception as e:
            logger.exception("[BFA] Falha crítica durante a sequência de boot: %s", e)

        yield

    logger.info("[BFA] Encerrando atividades do barramento de serviços.")


app = FastAPI(
    title="BFA Service Hub",
    description="Barramento de Descoberta Semântica Híbrida (FAISS + BM25) e Proxy MCP.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/skills")
def listar_skills() -> Dict[str, Any]:
    """Retorna o catálogo completo de habilidades indexadas na memória."""
    return AGENT_REGISTRY


@app.get("/resolve")
async def resolve(
    query: str = Query(..., description="Query em linguagem natural"),
    top_k: int = Query(3, description="Quantidade máxima de candidatos"),
    k_rrf: int = Query(60, description="Constante de penalização do algoritmo RRF"),
) -> Dict[str, Any]:
    """Resolve uma query em linguagem natural usando busca híbrida unificada."""
    result = await resolve_agent(query, top_k=top_k, k_rrf=k_rrf)
    if not result:
        return {"error": "no_confident_match", "best": None, "candidates": []}
    return result


@app.get("/resolve/agents")
async def resolve_agents(
    query: str = Query(..., description="Query direcionada a domínios de agentes"),
    top_k: int = Query(3, description="Quantidade máxima de candidatos"),
    k_rrf: int = Query(60, description="Constante de penalização RRF"),
) -> Dict[str, Any]:
    """Resolve a requisição filtrando estritamente por capacidades de agentes."""
    result = await resolve_agent(query, top_k=top_k, k_rrf=k_rrf, filter_type="agent")
    if not result:
        return {"error": "no_confident_match", "best": None, "candidates": []}
    return result


@app.get("/resolve/tools")
async def resolve_tools(
    query: str = Query(..., description="Query direcionada a esquemas de ferramentas"),
    top_k: int = Query(3, description="Quantidade máxima de candidatos"),
    k_rrf: int = Query(60, description="Constante de penalização RRF"),
) -> Dict[str, Any]:
    """Resolve a requisição filtrando estritamente por ferramentas (MCP/Smithery)."""
    result = await resolve_agent(query, top_k=top_k, k_rrf=k_rrf, filter_type="tool")
    if not result:
        return {"error": "no_confident_match", "best": None, "candidates": []}
    return result


@app.get("/skills/agents")
def listar_agents() -> Dict[str, Any]:
    """Filtra o catálogo trazendo apenas os metadados dos agentes especialistas."""
    return {k: v for k, v in AGENT_REGISTRY.items() if v.get("type") == "agent"}


@app.get("/skills/tools")
def listar_tools() -> Dict[str, Any]:
    """Filtra o catálogo trazendo as ferramentas locais (FastMCP) e externas."""
    return {k: v for k, v in AGENT_REGISTRY.items() if v.get("type") == "tool"}


# Monta o app streamable HTTP do MCP na rota desejada
app.mount("/mcp_gateway", mcp_app)


@app.get("/")
async def health() -> Dict[str, str]:
    """Endpoint de checagem de integridade (Health Check) para a malha do Docker."""
    return {"status": "ok", "service": "bfa_service_hub"}
