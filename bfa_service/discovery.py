"""Módulo de Infraestrutura de Rede responsável pela varredura e coleta bruta (A2A + MCP)."""

import asyncio
import json
import logging
import os
from typing import Dict, Any

import httpx
from a2a.client import A2ACardResolver

logger = logging.getLogger("bfa.discovery")

AGENT_ENDPOINTS = [
    "http://analyst-agent:5001",
    "http://auditor-agent:5002",
    "http://moderator-agent:5003",
]

SMITHERY_URL = os.getenv("SMITHERY_API_URL", "https://smithery.ai")
SMITHERY_API_KEY = os.getenv("SMITHERY_API_KEY", "")


async def run_global_scan() -> Dict[str, Dict[str, Any]]:
    """Varre a rede ia-mesh e retorna o mapa bruto de capacidades descobertas."""
    logger.info("[Discovery] Iniciando varredura bruta de rede...")
    raw_collected_data = {}

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Coleta dados estruturados dos Agentes e seus sub-apps MCP locais
        for base_url in AGENT_ENDPOINTS:
            agent_data = await _fetch_agent_data(client, base_url)
            raw_collected_data.update(agent_data)

        # 2. Coleta dados de ferramentas externas via Smithery Gateway
        if SMITHERY_API_KEY:
            smithery_data = await _fetch_smithery_data(client)
            raw_collected_data.update(smithery_data)

    return raw_collected_data


async def _fetch_agent_data(client: httpx.AsyncClient, base_url: str) -> Dict[str, Dict[str, Any]]:
    """Bate no endpoint do agente, extrai o AgentCard e mapeia o sub-app MCP."""
    local_registry = {}
    for attempt in range(3):
        try:
            resolver = A2ACardResolver(httpx_client=client, base_url=base_url)
            card = await resolver.get_agent_card()

            rpc_url = base_url + "/rpc"
            mcp_url = None

            for interface in card.supported_interfaces:
                if interface.protocol_binding == "JSONRPC":
                    rpc_url = interface.url
                elif interface.protocol_binding == "MCP_HTTP":
                    mcp_url = interface.url

            # Mapeia as Skills Cognitivas de domínio do Agente
            for skill in card.skills:
                skill_id = f"agent://{skill.id}"
                local_registry[skill_id] = {
                    "name": skill.name,
                    "description": skill.description,
                    "tags": skill.tags,
                    "type": "agent",
                    "execution_url": rpc_url,
                    "input_schema": None,
                }

            # Se houver um endpoint MCP federado (/mcp), coleta as ferramentas internas
            if mcp_url:
                tools_response = await client.get(f"{mcp_url}/tools")
                if tools_response.status_code == 200:
                    tools = tools_response.json()
                    if isinstance(tools, str):
                        tools = json.loads(tools)

                    for tool in tools:
                        tool_name = tool.get("name")
                        tool_id = f"tool://{tool_name}"
                        tags = tool.get("annotations", {}).get("tags", ["mcp", "local"])

                        local_registry[tool_id] = {
                            "name": tool_name,
                            "description": tool.get("description", ""),
                            "tags": tags,
                            "type": "tool",
                            "execution_url": mcp_url,
                            "input_schema": json.dumps(tool.get("inputSchema", {})),
                        }
            break

        # CORREÇÃO: Capturando erros específicos de rede e parseamento
        except (httpx.RequestError, json.JSONDecodeError, ValueError) as e:
            logger.warning("[Discovery] Tentativa %d falhou para %s: %s", attempt + 1, base_url, e)
            await asyncio.sleep(2.0)

    return local_registry


async def _fetch_smithery_data(client: httpx.AsyncClient) -> Dict[str, Dict[str, Any]]:
    """Bate na API do Smithery e coleta as ferramentas de prateleira externa."""
    smithery_registry = {}
    endpoint = f"{SMITHERY_URL}?api_key={SMITHERY_API_KEY}"
    try:
        response = await client.get(f"{endpoint}/tools")
        if response.status_code == 200:
            tools = response.json()
            for tool in tools:
                tool_name = tool.get("name")
                tool_id = f"tool://{tool_name}"
                tags = ["mcp", "external", "search"] if "search" in tool_name else ["mcp"]

                smithery_registry[tool_id] = {
                    "name": tool_name,
                    "description": tool.get("description", ""),
                    "tags": tags,
                    "type": "tool",
                    "execution_url": endpoint,
                    "input_schema": json.dumps(tool.get("inputSchema", {})),
                }

    # CORREÇÃO: Capturando erros específicos de rede e parseamento
    except (httpx.RequestError, json.JSONDecodeError) as e:
        logger.error("[Discovery] Erro ao consumir Smithery MCP: %s", e)

    return smithery_registry
