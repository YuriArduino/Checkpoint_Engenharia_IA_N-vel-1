"""Server do agente pesquisador de políticas (Auditor Agent)."""

from starlette.applications import Starlette
from mcp.server.fastmcp import FastMCP

from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

# v1.0: Contratos e tipagens nativas do protocolo A2A
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, AgentInterface

# RESOLVIDO: Imports absolutos ancorados na raiz do container do agente
from executor import PolicyAuditExecutor
from metadata import AUDITOR_SKILL_DESC, AUDITOR_CARD_DESC

# ============================================================================
# 1. SERVIDOR MCP INTERNO DO AGENTE (Federated MCP Isolation)
# ============================================================================
# O agente encapsula suas próprias capacidades sem depender de um hub de recursos
mcp_server = FastMCP("AuditorInternalTools")


@mcp_server.tool()
def get_auditor_metadata() -> str:
    """Retorna metadados operacionais e escopo do Auditor Agent."""
    return "Auditor v1.0: Focado em cruzamento e validação de diretrizes da comunidade."


# ============================================================================
# 2. CONFIGURAÇÃO DO CONTRATO A2A V1.0 (Agent Card)
# ============================================================================
skill = AgentSkill(
    id="policy_audit",
    name="Auditoria de Políticas",
    description=AUDITOR_SKILL_DESC,
    tags=["auditoria", "politicas", "diretrizes", "pesquisa", "regras"],
    examples=[
        "pesquise as regras aplicáveis a este caso",
        "encontre políticas sobre spam na comunidade",
    ],
    input_modes=["text"],
    output_modes=["text"],
)

capabilities = AgentCapabilities(streaming=False, push_notifications=False)

agent_card = AgentCard(
    name="Agente Pesquisador de Políticas",
    description=AUDITOR_CARD_DESC,
    version="1.0.0",
    capabilities=capabilities,
    skills=[skill],
    default_input_modes=["text"],
    default_output_modes=["text"],
    supported_interfaces=[
        # Interface 1: Ponto de entrada para o Orquestrador via gRPC/JSONRPC (Porta 5002)
        AgentInterface(
            url="http://auditor-agent:5002/rpc",
            protocol_binding="JSONRPC",
        ),
        # Interface 2: Ponto de descoberta para o BFA extrair o schema do FastMCP
        AgentInterface(
            url="http://auditor-agent:5002/mcp",
            protocol_binding="MCP_HTTP",
        ),
    ],
)

# ============================================================================
# 3. MONTAGEM DA APLICAÇÃO STARLETTE UNIFICADA
# ============================================================================
handler = DefaultRequestHandler(
    agent_executor=PolicyAuditExecutor(),
    task_store=InMemoryTaskStore(),
    agent_card=agent_card,
)

card_routes = create_agent_card_routes(agent_card=agent_card)
rpc_routes = create_jsonrpc_routes(request_handler=handler, rpc_url="/rpc")

# 1. Método oficial da SDK (mcp.server.fastmcp) para expor a aplicação ASGI
mcp_asgi = mcp_server.sse_app()

# 2. Definição do roteamento unificado do Starlette carregando o ciclo de vida (lifespan)
app = Starlette(
    routes=[
        *card_routes,
        *rpc_routes,
    ],
    lifespan=mcp_asgi.router.lifespan_context,
)

# 3. Acopla o sub-aplicativo MCP na rota esperada pelo AgentCard
app.mount("/mcp", mcp_asgi)
