"""Schemas Pydantic para o Orquestrador de Moderação de Conteúdo."""

from typing import Optional

from pydantic import BaseModel, Field


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
