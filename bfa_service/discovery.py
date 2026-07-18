"""Módulo de Service Discovery para indexação dinâmica de Agent Cards e Ferramentas MCP."""

import asyncio
from typing import Dict, Any
import json
import logging
import httpx

logger = logging.getLogger(__name__)

# NOTA: Verifique se no seu docker-compose.yml o nome do serviço (service)
# é com underline (_) ou traço (-). Se for "analyst-agent", troque aqui!
DEFAULT_AGENT_URLS = [
    "http://analyst-agent:5001",
    "http://auditor-agent:5002",
    "http://moderator-agent:5003",
]


async def run_global_scan(agent_urls: list[str] | None = None) -> Dict[str, Any]:
    """Varre os endpoints dos agentes cadastrados para centralizar capacidades e ferramentas.

    Realiza chamadas assíncronas HTTP REST para extrair o .well-known/agent-card.json
    e mapear as ferramentas expostas via MCP na rota customizada /mcp/tools.
    Possui tolerância a falhas na inicialização (retry).
    """
    if agent_urls is None:
        agent_urls = DEFAULT_AGENT_URLS

    local_registry: Dict[str, Any] = {}
    max_retries = 5  # Quantidade máxima de tentativas por agente
    retry_delay = 3  # Segundos de espera entre as tentativas

    async with httpx.AsyncClient(timeout=5.0) as client:
        for url in agent_urls:
            base_url = url.rstrip("/")
            card_endpoint = f"{base_url}/.well-known/agent-card.json"

            mcp_url = None
            agent_ready = False

            # -----------------------------------------------------------------
            # Fase 1: Coleta do Agent Card com mecanismo de Retry
            # -----------------------------------------------------------------
            for attempt in range(max_retries):
                logger.info(
                    "[Discovery] Buscando Agent Card em: %s (Tentativa %d/%d)",
                    card_endpoint,
                    attempt + 1,
                    max_retries,
                )
                try:
                    response = await client.get(card_endpoint)
                    if response.status_code == 200:
                        card_data = response.json()
                        agent_name = card_data.get("name", "Agente Desconhecido")
                        logger.info("[Discovery] Agent Card obtido com sucesso de '%s'", agent_name)

                        interfaces = card_data.get("supportedInterfaces", [])
                        for interface in interfaces:
                            if interface.get("protocolBinding") == "MCP_HTTP":
                                mcp_url = interface.get("url")
                                break

                        agent_ready = True
                        break  # Sai do loop de tentativas pois deu certo
                    else:
                        logger.warning(
                            "[Discovery] Falha ao obter card de %s (Status: %s)",
                            card_endpoint,
                            response.status_code,
                        )
                        break  # Se o erro for de HTTP (ex: 404),

                except httpx.HTTPError as e:
                    if attempt < max_retries - 1:
                        logger.warning(
                            "[Discovery] O agente %s ainda não está pronto. Aguardando %ds...",
                            base_url,
                            retry_delay,
                        )
                        await asyncio.sleep(retry_delay)
                    else:
                        logger.error(
                            "[Discovery] Erro de rede definitivo ao acessar %s: %s",
                            card_endpoint,
                            str(e),
                        )

            if not agent_ready:
                continue  # Pula para o próximo agente da lista se este falhou de vez

            # -----------------------------------------------------------------
            # Fase 2: Coleta de Ferramentas via Endpoint REST
            # -----------------------------------------------------------------
            if mcp_url:
                tools_endpoint = f"{mcp_url.rstrip('/')}/tools"
                logger.info("[Discovery] Indexando ferramentas MCP via REST em: %s", tools_endpoint)

                try:
                    tools_response = await client.get(tools_endpoint)
                    if tools_response.status_code == 200:
                        payload = tools_response.json()
                        tools_list = payload.get("tools", [])

                        for tool in tools_list:
                            tool_name = tool.get("name")
                            if not tool_name:
                                continue

                            tool_id = f"tool://{tool_name}"

                            local_registry[tool_id] = {
                                "name": tool_name,
                                "description": tool.get("description", ""),
                                "tags": ["mcp", "local", "stateless"],
                                "type": "tool",
                                "execution_url": mcp_url,
                                "input_schema": json.dumps(tool.get("inputSchema", {})),
                            }
                            logger.info(
                                "[Discovery] Ferramenta '%s' registrada com sucesso.", tool_id
                            )
                    else:
                        logger.warning(
                            "[Discovery] Endpoint de ferramentas %s retornou HTTP %s",
                            tools_endpoint,
                            tools_response.status_code,
                        )
                except httpx.HTTPError as mcp_err:
                    logger.warning(
                        "[Discovery] Falha ao coletar ferramentas REST em %s: %s",
                        tools_endpoint,
                        str(mcp_err),
                    )

    return local_registry
