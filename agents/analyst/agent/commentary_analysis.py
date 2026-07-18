"""Agente Analista responsável por processar o comentário inicial do aluno (Stateless / PnP)."""

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
class AnalisadorOutput(BaseModel):
    """Schema estrito para o output cognitivo estruturado do Analista."""

    classificacao: str = Field(
        ...,
        description="Classificação estrita: 'positivo', 'neutro' ou 'potencialmente problemático'.",
    )
    analise_do_agente: str = Field(
        ...,
        description="Justificativa do teor do texto (ex: se parece spam, ofensivo, dúvida, etc.).",
    )


# Acopla a saída estruturada diretamente na LLM conforme as diretrizes
__llm_structured = __llm.with_structured_output(AnalisadorOutput)

client = MultiServerMCPClient(
    {  # type: ignore
        "bfa_gateway": {
            "transport": "http",
            "url": "http://bfa-service:8001/mcp_gateway",
        },
    }
)

_CACHE: Dict[str, Optional[Any]] = {"agente": None}


async def build_analyst_agent():
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
            Você é o Agente Analisador de uma plataforma de cursos online.
            Sua única função é ler o comentário original e extrair o contexto.

            TAREFAS OBRIGATÓRIAS:
            1. Definir a classificação: 'positivo', 'neutro' ou 'potencialmente problemático'.
            2. Escrever a justificativa diagnóstica do teor do texto.

            REGRAS DE OURO:
            - VOCÊ NÃO MODERA NEM DECIDE NADA. Faça apenas a leitura clínica.
        """),
    )
    return _CACHE["agente"]


async def run_analyst_agent(comentario_original: str) -> Dict[str, str]:
    """Passada Única de Inferência: Sem manter histórico na camada do agente."""
    agent = await build_analyst_agent()

    resultado = await agent.ainvoke({"messages": [HumanMessage(content=comentario_original)]})

    # 4. Captura o dado parseado na chave exigida pela arquitetura
    structured_response: AnalisadorOutput = resultado["structured_response"]

    return {
        "classificacao": structured_response.classificacao,
        "analise_do_agente": structured_response.analise_do_agente,
    }
