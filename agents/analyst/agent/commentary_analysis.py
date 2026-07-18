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

# LLM instanciada com configuração limpa (sem bind_tools ou with_structured_output)
__llm = ChatOpenAI(
    model=model_name,
    temperature=float(os.getenv("CHAT_TEMPERATURE", "0.0")),
    top_p=float(os.getenv("CHAT_TOP_P", "0.90")),
)


# 1. Contrato de Saída Rígido
class CommentaryAnalysisOutput(BaseModel):
    """Schema estrito para o output da análise de comentários."""

    sentimento: str = Field(
        ...,
        description="Sentimento geral: 'positivo', 'negativo' ou 'neutro'.",
    )
    intencao: str = Field(
        ...,
        description="Intenção principal: 'dúvida', 'reclamação', 'elogio', 'sugestão' etc.",
    )
    analise_detalhada: str = Field(
        ...,
        description=("Análise completa e justificativa da classificação."),
    )


# Cliente MCP para ferramentas (type: ignore para contornar verificação de tipo de Connection)
client = MultiServerMCPClient(
    {  # type: ignore
        "bfa_gateway": {
            "transport": "http",
            "url": "http://bfa-service:8001/mcp_gateway",
        },
    }
)

_CACHE: Dict[str, Optional[Any]] = {"agente": None}


async def build_commentary_agent():
    """Instancia o agente de forma puramente funcional, sem checkpointer local."""
    if _CACHE["agente"] is not None:
        return _CACHE["agente"]

    try:
        tools = await client.get_tools()
    except (OSError, RuntimeError) as e:
        print(f"[Aviso] Não foi possível conectar ao BFA/MCP no momento: {e}")
        tools = []

    # 2. Inicialização via factory unificada – CORREÇÃO AQUI
    #    Passamos __llm (BaseChatModel), NÃO um Runnable.
    _CACHE["agente"] = create_agent(
        model=__llm,  # <-- modelo puro
        tools=tools,
        response_format=CommentaryAnalysisOutput,  # saída estruturada
        system_prompt=("""
            Você é um analista de comentários de uma plataforma de cursos online.
            Sua tarefa é analisar o comentário fornecido e retornar um parecer estruturado.

            TAREFAS OBRIGATÓRIAS:
            1. Classificar o sentimento (positivo, negativo ou neutro).
            2. Identificar a intenção principal do comentário.
            3. Fornecer uma análise detalhada que justifique as classificações.

            REGRAS DE OURO:
            - Seja preciso e direto.
            - Baseie sua análise exclusivamente no conteúdo do comentário.
        """),
    )
    return _CACHE["agente"]


async def run_analysis_agent(
    comentario_original: str, _thread_id: Optional[str] = None
) -> Dict[str, str]:
    agent = await build_commentary_agent()

    input_text = f"Comentário a analisar: {comentario_original}"

    # O ainvoke roda limpo sem o configurable interno de memória local
    resultado = await agent.ainvoke({"messages": [HumanMessage(content=input_text)]})

    structured_response: CommentaryAnalysisOutput = resultado["structured_response"]
    return {
        "sentimento": structured_response.sentimento,
        "intencao": structured_response.intencao,
        "analise_detalhada": structured_response.analise_detalhada,
    }
