"""Server do agente de análise semântica e comportamental (Analyst Agent)."""

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP

from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

# v1.0: Contratos e tipagens nativas do protocolo A2A
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, AgentInterface

# Importa o executor específico do Analyst e os metadados
from .executor import CommentaryAnalysisExecutor
from .metadata import ANALYST_SKILL_DESC, ANALYST_CARD_DESC

# ============================================================================
# 1. SERVIDOR MCP INTERNO DO AGENTE (Federated MCP Isolation)
# ============================================================================
mcp_server = FastMCP("AnalystInternalTools")


@mcp_server.tool()
def get_analyst_metadata() -> str:
    """Retorna metadados operacionais e escopo do Analyst Agent."""
    return "Analyst v1.0: Focado em detecção semântica de spam, ofensas e toxicidade."


# ============================================================================
# 2. CONFIGURAÇÃO DO CONTRATO A2A V1.0 (Agent Card)
# ============================================================================
skill = AgentSkill(
    id="commentary_analysis",
    name="Análise Multidimensional de Comentários",
    description=ANALYST_SKILL_DESC,
    tags=["analise", "sentimento", "urgencia", "spam", "detectar problemas"],
    examples=[
        "analise a urgência e o sentimento deste comentário",
        "verifique se o aluno postou algum problema ou link proibido",
    ],
    input_modes=["text"],
    output_modes=["text"],
)

capabilities = AgentCapabilities(streaming=False, push_notifications=False)

agent_card = AgentCard(
    name="Agente Analista de Moderação",
    description=ANALYST_CARD_DESC,
    version="1.0.0",
    capabilities=capabilities,
    skills=[skill],
    default_input_modes=["text"],
    default_output_modes=["text"],
    supported_interfaces=[
        # Interface 1: Ponto de entrada para o Orquestrador via gRPC/JSONRPC
        AgentInterface(
            url="http://analyst-agent:5001/rpc",
            protocol_binding="JSONRPC",
        ),
        # Interface 2: Ponto de descoberta para o BFA extrair o schema do FastMCP
        AgentInterface(
            url="http://analyst-agent:5001/mcp",
            protocol_binding="MCP_HTTP",
        ),
    ],
)

# ============================================================================
# 3. MONTAGEM DA APLICAÇÃO STARLETTE UNIFICADA
# ============================================================================
handler = DefaultRequestHandler(
    agent_executor=CommentaryAnalysisExecutor(),
    task_store=InMemoryTaskStore(),
    agent_card=agent_card,
)

card_routes = create_agent_card_routes(agent_card=agent_card)
rpc_routes = create_jsonrpc_routes(request_handler=handler, rpc_url="/rpc")

# Método oficial da SDK (mcp.server.fastmcp) para expor a aplicação ASGI
mcp_asgi = mcp_server.sse_app()


async def get_tools(_request):
    """Retorna a lista de ferramentas disponíveis para o Orquestrador (Agent Orchestrator)."""
    return JSONResponse(
        {
            "tools": [
                {
                    "name": "get_analyst_metadata",
                    "description": "Analyst v1.0: Focado em análise multidimensional de comentários.",
                    "inputSchema": {"type": "object", "properties": {}, "required": []},
                }
            ]
        }
    )


# CORREGIDO: Removida a rota '/mcp/tools' do construtor principal para evitar a colisão de rede
app = Starlette(
    routes=[
        *card_routes,
        *rpc_routes,
    ],
    lifespan=mcp_asgi.router.lifespan_context,
)

# CORREGIDO: Adiciona a rota customizada diretamente no escopo do sub-app montado
# Isso resolve o loop de roteamento e destrava o container instantaneamente
mcp_asgi.router.add_route("/tools", get_tools, methods=["GET"])

# Monta o ecossistema federado na rota combinada
app.mount("/mcp", mcp_asgi)
