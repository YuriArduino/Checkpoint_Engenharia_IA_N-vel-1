"""Agente Revisor que consolida as informações e recomenda uma ação (Stateless / PnP)."""

import os
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

model_name = os.getenv("CHAT_MODEL") or "gpt-4o-mini"

# LLM instanciada com configuração limpa
__llm = ChatOpenAI(
    model=model_name,
    temperature=float(os.getenv("CHAT_TEMPERATURE", "0.0")),
    top_p=float(os.getenv("CHAT_TOP_P", "0.90")),
)


# 1. Contrato de Saída Rígido
class RevisorOutput(BaseModel):
    """Schema estrito para o output cognitivo estruturado do Revisor de Moderação."""

    recomendacao_acao: str = Field(
        ...,
        description=(
            "A ação sugerida: 'Aprovar', 'Remover por Spam', 'Remover por Ofensa', "
            "'Editar por linguagem inadequada', etc."
        ),
    )
    justificativa: str = Field(
        ...,
        description=(
            "A consolidação da análise e das políticas que fundamentam essa recomendação."
        ),
    )


# Acopla a saída estruturada diretamente na LLM conforme as diretrizes
__llm_structured = __llm.with_structured_output(RevisorOutput)

client = MultiServerMCPClient(
    {  # type: ignore
        "bfa_gateway": {
            "transport": "http",
            "url": "http://bfa-service:8001/mcp_gateway",
        },
    }
)

_CACHE: Dict[str, Optional[Any]] = {"agente": None}


async def build_revisor_agent():
    """Instancia o agente de forma puramente funcional, sem checkpointer local."""
    if _CACHE["agente"] is not None:
        return _CACHE["agente"]

    try:
        tools = await client.get_tools()
    except (OSError, RuntimeError) as e:
        print(f"[Aviso] Não foi possível conectar ao BFA/MCP no momento: {e}")
        tools = []

    # 2. Inicialização via factory unificada
    _CACHE["agente"] = create_agent(
        model=__llm,
        tools=tools,
        system_prompt=("""
            Você é o Agente Revisor de uma plataforma de cursos online.
            Você receberá a 'analise_do_agente' e as 'politicas_relevantes'.

            TAREFAS OBRIGATÓRIAS:
            1. Consolidar os dados da análise com as políticas encontradas.
            2. Gerar uma recomendação de ação clara e direta para o moderador humano aprovar ou revisar.

            REGRAS DE OURO:
            - Formate a 'recomendacao_acao' de forma objetiva (ex: 'Aprovar', 'Remover por [motivo]').
            - Na justificativa, deixe evidente como a política se aplica à análise.
        """),
    )
    return _CACHE["agente"]


async def run_revisor_agent(analise_do_agente: str, politicas_relevantes: str) -> Dict[str, str]:
    """Passada Única de Inferência: Sem manter histórico na camada do agente."""
    agent = await build_revisor_agent()

    input_text = (
        f"Análise do Agente: {analise_do_agente}\n" f"Políticas Relevantes: {politicas_relevantes}"
    )

    resultado = await agent.ainvoke({"messages": [HumanMessage(content=input_text)]})

    # 4. Captura o dado parseado na chave exigida pela arquitetura
    structured_response: RevisorOutput = resultado["structured_response"]

    return {
        "recomendacao_acao": structured_response.recomendacao_acao,
        "justificativa": structured_response.justificativa,
    }
