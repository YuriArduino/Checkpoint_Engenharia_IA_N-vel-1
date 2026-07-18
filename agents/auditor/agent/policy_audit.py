"""Agente Pesquisador responsável por buscar diretrizes caso haja problema (Stateless / PnP)."""

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
    temperature=float(os.getenv("CHAT_TEMPERATURE", "0.2")),
    top_p=float(os.getenv("CHAT_TOP_P", "0.90")),
)


# 1. Contrato de Saída Rígido
class PesquisadorOutput(BaseModel):
    """Schema estrito para o output cognitivo estruturado do Pesquisador."""

    politicas_relevantes: str = Field(
        ...,
        description=(
            "Trechos das diretrizes da comunidade encontrados via pesquisa que se "
            "aplicam ao caso, ou 'Nenhuma política necessária' se não houver problema."
        ),
    )


# Acopla a saída estruturada diretamente na LLM conforme as diretrizes
__llm_structured = __llm.with_structured_output(PesquisadorOutput)

client = MultiServerMCPClient(
    {  # type: ignore
        "bfa_gateway": {
            "transport": "http",
            "url": "http://bfa-service:8001/mcp_gateway",
        },
    }
)

_CACHE: Dict[str, Optional[Any]] = {"agente": None}


async def build_researcher_agent():
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
            Você é o Agente Pesquisador de Políticas de uma plataforma de cursos.
            Você receberá uma 'classificacao' e uma 'analise_do_agente'.

            TAREFAS OBRIGATÓRIAS:
            1. Se a classificação for 'potencialmente problemático', USE OBRIGATORIAMENTE sua ferramenta de busca (Tavily/MCP) para pesquisar as diretrizes da comunidade ou regras de convivência em fóruns online.
            2. Retorne o texto das políticas relevantes que se aplicam ao problema apontado na análise.
            3. Se o comentário for 'positivo' ou 'neutro', não pesquise nada e apenas retorne "Nenhuma política necessária".

            REGRAS DE OURO:
            - Seu papel é fornecer embasamento legal/comunitário. Não julgue o comentário, apenas traga a regra.
        """),
    )
    return _CACHE["agente"]


async def run_researcher_agent(classificacao: str, analise_do_agente: str) -> Dict[str, str]:
    """Passada Única de Inferência: Sem manter histórico na camada do agente."""
    agent = await build_researcher_agent()

    input_text = f"Classificação: {classificacao}\nAnálise do Agente: {analise_do_agente}"

    resultado = await agent.ainvoke({"messages": [HumanMessage(content=input_text)]})

    # 4. Captura o dado parseado na chave exigida pela arquitetura
    structured_response: PesquisadorOutput = resultado["structured_response"]

    return {
        "politicas_relevantes": structured_response.politicas_relevantes,
    }
