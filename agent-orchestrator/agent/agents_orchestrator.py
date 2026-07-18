"""Módulo Supervisor de Moderação - Orquestração e Estado Persistente."""

import json
import logging
import os
import sqlite3
from typing import Any, Dict, cast

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

# Correção: Agora usamos o SQLite para persistência real
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.base import empty_checkpoint, CheckpointMetadata

logger = logging.getLogger(__name__)
load_dotenv()

# ==========================================================
# Configuração do Banco de Dados de Checkpoints (SQLite)
# ==========================================================
# O arquivo será criado na pasta do projeto
DB_PATH = "moderation_checkpoints.db"
connection = sqlite3.connect(DB_PATH, check_same_thread=False)
memory: SqliteSaver = cast(SqliteSaver, SqliteSaver(connection))

# ==========================================================
# Configuração do Modelo (Analista de Moderação)
# ==========================================================
model_name = os.getenv("CHAT_MODEL") or "gpt-4o-mini"
__llm = ChatOpenAI(model=model_name, temperature=0.0)

# ==========================================================
# Estrutura para Controle do Fluxo
# ==========================================================


async def classificar_comentario(query: str) -> Dict[str, str]:
    """Analisa o comentário para definir se precisa de intervenção humana."""
    prompt = f"""
    Analise o seguinte comentário de um aluno e classifique-o:
    Texto: "{query}"

    Responda estritamente em JSON:
    {{
        "classificacao": "positivo" | "neutro" | "potencialmente_problematico",
        "justificativa": "Razão da classificação"
    }}
    """
    # Usaremos a mesma lógica de structured output ou parse que definimos antes
    resposta = await __llm.ainvoke([HumanMessage(content=prompt)])
    texto = resposta if isinstance(resposta, str) else getattr(resposta, "content", str(resposta))

    try:
        dados = json.loads(texto)
        return {
            "classificacao": dados.get("classificacao", "neutro"),
            "justificativa": dados.get("justificativa", "Análise pendente"),
        }
    except json.JSONDecodeError:
        logger.warning("Resposta do LLM não estava em JSON. Texto recebido: %s", texto)
        return {
            "classificacao": "neutro",
            "justificativa": "Não foi possível parsear a resposta do modelo.",
        }


# ==========================================================
# Resolução de Contexto Integrada com LangGraph (SQLite)
# ==========================================================


async def preparar_contexto_moderacao(thread_id: str) -> Dict[str, Any]:
    """
    Recupera o estado atual da thread no SQLite para o Frontend.
    Isso permite que o AG-UI saiba se o comentário está em 'análise',
    'aguardando_humano' ou 'aprovado'.
    """
    config: RunnableConfig = cast(
        RunnableConfig, {"configurable": {"thread_id": thread_id}}
    )

    # 1. Recupera o snapshot do SQLite
    checkpoint = cast(Dict[str, Any], memory.get(config) or empty_checkpoint())

    # 2. Extrai estado persistido
    channel_values = checkpoint.get("channel_values", {})
    state = channel_values.get("state", {})

    logger.info("Recuperado estado para thread %s: %s", thread_id, state)
    return state


# ==========================================================
# Utilitários de Gerenciamento
# ==========================================================


def salvar_checkpoint_manual(thread_id: str, novo_estado: Dict[str, Any]):
    """
    Útil para quando o moderador humano faz uma alteração via API
    e precisamos injetar esse estado manualmente no grafo.
    """
    config: RunnableConfig = cast(
        RunnableConfig, {"configurable": {"thread_id": thread_id}}
    )
    checkpoint = cast(Dict[str, Any], memory.get(config) or empty_checkpoint())

    # Atualiza o estado no checkpoint
    checkpoint["channel_values"]["state"] = novo_estado

    # Salva
    meta = cast(
        CheckpointMetadata,
        {"source": "human_intervention", "step": 1},
    )
    memory.put(config, checkpoint, metadata=meta, new_versions={})
    logger.info("Estado manualmente atualizado via moderador para thread %s", thread_id)
