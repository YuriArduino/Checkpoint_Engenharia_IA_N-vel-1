"""Aplicação FastAPI principal para o ecossistema do BFA Service Hub."""

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse

from database import init_db
from registry import AGENT_REGISTRY, build_index, resolve_agent

logger = logging.getLogger("bfa.app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Gerenciador de ciclo de vida assíncrono para o barramento do BFA."""
    logger.info("[BFA] Inicializando subsistemas do barramento central...")

    # 1. Garante a inicialização da tabela estruturada no SQLite compartilhado
    init_db()

    # 2. Executa a varredura de rede, ingestão no banco e compilação FAISS + BM25 RRF
    try:
        await build_index()
        logger.info("[BFA] Catálogo de habilidades e índices gerados com sucesso.")
    # Correção (W0718): Em rotinas de boot, capturar exceções genéricas
    # é esperado para evitar crash silencioso.
    # pylint: disable=broad-exception-caught
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
# Correção: Rota transformada em async para aguardar a corrotina
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
# Correção: Rota transformada em async para aguardar a corrotina
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
# Correção: Rota transformada em async para aguardar a corrotina
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


@app.post("/mcp_gateway")
async def mcp_gateway(payload: Dict[str, Any]) -> JSONResponse:
    """Gateway Proxy Unificado para roteamento desacoplado de chamadas MCP."""
    method = payload.get("method")
    params = payload.get("params", {})

    if not method:
        raise HTTPException(status_code=400, detail="Propriedade 'method' é obrigatória.")

    logger.info("[BFA Proxy] Roteando execução de ferramenta: %s", method)

    # 1. Identifica se a ferramenta pertence ao domínio externo do Smithery (Tavily)
    if "tavily" in method:
        # Se for externa, o próprio barramento executa de forma abstrata
        return JSONResponse(
            content={"result": f"Executado proxy externo para {method} com params {params}"}
        )

    # 2. Se for uma ferramenta interna de um agente, devolve um redirecionamento
    return JSONResponse(
        status_code=501,
        content={"error": "Roteamento de execução interna não implementado neste nó."},
    )


@app.get("/")
async def health() -> Dict[str, str]:
    """Endpoint de checagem de integridade (Health Check) para a malha do Docker."""
    return {"status": "ok", "service": "bfa_service_hub"}
