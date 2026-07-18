"""Metadados e descrições semânticas do Agente Revisor de Decisões (Moderator Agent)."""

MODERATOR_SKILL_DESC = (
    "Especialista em consolidação analítica e recomendação de ações de moderação.\n\n"
    "CAPACIDADES COGNITIVAS MAPEADAS:\n"
    "1. [consolidar_analise_e_politicas]\n"
    "   - Descrição: Cruza o diagnóstico clínico do texto com o embasamento legal obtido.\n"
    "   - Entrada: analise_do_agente (string), politicas_relevantes (string).\n"
    "   - Retorno: Texto explicativo contextualizando a infração ou conformidade.\n\n"
    "2. [gerar_recomendacao_moderacao]\n"
    "   - Descrição: Determina a ação objetiva final ideal para o moderador humano.\n"
    "   - Entrada: analise_do_agente (string), politicas_relevantes (string).\n"
    "   - Retorno: Ação estrita (Aprovar, Remover, Editar, Suspender Conta, etc.)."
)

MODERATOR_CARD_DESC = (
    "Responsável por fundir o diagnóstico clínico com o embasamento normativo, "
    "gerando recomendações estritas e justificadas para a tomada de decisão humana."
)
