"""Schemas Pydantic para o Orquestrador de Moderação de Conteúdo."""

from typing import Optional, List, Annotated
from pydantic import BaseModel, Field

from langgraph.graph.message import add_messages


class ChatRequest(BaseModel):
    """Schema da requisição inicial vinda do Frontend (AG-UI)."""

    message: str = Field(..., description="O comentário do aluno a ser analisado.")
    thread_id: str = Field(..., description="ID da sessão para persistência no LangGraph.")


class HumanInterventionRequest(BaseModel):
    """Schema para a intervenção direta do moderador no estado (HitL)."""

    thread_id: str = Field(..., description="ID da thread pausada.")
    nova_classificacao: str = Field(..., description="Aprovar, remover ou editar.")
    nova_justificativa: Optional[str] = Field(None, description="Justificativa do humano.")
    comentario_editado: Optional[str] = Field(
        None, description="Versão editada do comentário, se houver."
    )


class ModerationState(BaseModel):
    """Estado mutável persistido no SQLite que trafega entre os nós do LangGraph."""

    comentario_original: str = Field(..., description="O texto bruto original do aluno.")
    thread_id: str = Field(..., description="ID exclusivo da sessão gerenciada pelo checkpointer.")

    # APLICAÇÃO CORRETA: Redutor associado via tipagem anotada para controle de tokens
    messages: Annotated[list, add_messages] = Field(default_factory=list)

    classificacao: Optional[str] = Field(None)
    analise_do_agente: Optional[str] = Field(None)
    politicas_relevantes: List[str] = Field(default_factory=list)
    recomendacao_acao: Optional[str] = Field(None)
    justificativa_moderacao: Optional[str] = Field(None)
    decisao_final_humano: Optional[str] = Field(None)
    justificativa_humano: Optional[str] = Field(None)
    comentario_final_aprovado: Optional[str] = Field(None)
