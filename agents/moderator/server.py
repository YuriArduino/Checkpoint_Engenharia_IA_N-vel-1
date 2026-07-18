"""Server do agente revisor de decisões (Moderator Agent)."""

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP

from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

# v1.0: Contratos e tipagens nativas do protocolo A2A
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, AgentInterface

# RESOLVIDO: Imports absolutos ancorados na raiz do container do agente
from .executor import DecisionModerationExecutor
from .metadata import MODERATOR_SKILL_DESC, MODERATOR_CARD_DESC

# ============================================================================
# 1. SERVIDOR MCP INTERNO DO AGENTE (Federated MCP Isolation)
# ============================================================================
mcp_server = FastMCP("ModeratorInternalTools")


@mcp_server.tool()
def get_moderator_metadata() -> str:
    """Retorna metadados operacionais e escopo do Moderator Agent."""
    return "Moderator v1.0: Focado em consolidação analítica e recomendação final de ações."


# ============================================================================
# 2. CONFIGURAÇÃO DO CONTRATO A2A V1.0 (Agent Card)
# ============================================================================
skill = AgentSkill(
    id="decision_moderation",
    name="Revisão e Recomendação",
    description=MODERATOR_SKILL_DESC,
    tags=["moderacao", "decisao", "recomendacao", "revisao"],
    examples=[
        "qual a recomendação para este caso?",
        "consolide a análise e as políticas em uma ação direta",
    ],
    input_modes=["text"],
    output_modes=["text"],
)

capabilities = AgentCapabilities(streaming=False, push_notifications=False)

agent_card = AgentCard(
    name="Agente Revisor de Moderação",
    description=MODERATOR_CARD_DESC,
    version="1.0.0",
    capabilities=capabilities,
    skills=[skill],
    default_input_modes=["text"],
    default_output_modes=["text"],
    supported_interfaces=[
        AgentInterface(
            url="http://moderator-agent:5003/rpc",
            protocol_binding="JSONRPC",
        ),
        AgentInterface(
            url="http://moderator-agent:5003/mcp",
            protocol_binding="MCP_HTTP",
        ),
    ],
)

# ============================================================================
# 3. MONTAGEM DA APLICAÇÃO STARLETTE UNIFICADA
# ============================================================================
handler = DefaultRequestHandler(
    agent_executor=DecisionModerationExecutor(),
    task_store=InMemoryTaskStore(),
    agent_card=agent_card,
)

card_routes = create_agent_card_routes(agent_card=agent_card)
rpc_routes = create_jsonrpc_routes(request_handler=handler, rpc_url="/rpc")

# Método oficial da SDK (mcp.server.fastmcp) para expor a aplicação ASGI
mcp_asgi = mcp_server.sse_app()


async def get_tools(_request):
    """Retorna a lista de ferramentas disponíveis para o Moderator (Agent Reviewer)."""
    return JSONResponse(
        {
            "tools": [
                {
                    "name": "get_moderator_metadata",
                    "description": "Moderator v1.0: Consolidated moderation and policy enforcement agent.",
                    "inputSchema": {"type": "object", "properties": {}, "required": []},
                }
            ]
        }
    )


app = Starlette(
    routes=[
        *card_routes,
        *rpc_routes,
        Route("/mcp/tools", get_tools, methods=["GET"]),
    ],
    lifespan=mcp_asgi.router.lifespan_context,
)
app.mount("/mcp", mcp_asgi)
