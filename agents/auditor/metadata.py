"""Metadados e descrições semânticas do Agente Pesquisador de Políticas (Auditor Agent)."""

AUDITOR_SKILL_DESC = (
    "Especialista em pesquisa de diretrizes comunitárias e auditoria de conformidade.\n\n"
    "CAPACIDADES COGNITIVAS MAPEADAS:\n"
    "1. [pesquisar_diretrizes_comunidade]\n"
    "   - Descrição: Busca e localiza regras de convivência e termos de uso aplicáveis.\n"
    "   - Entrada: classificacao (string), analise_do_agente (string).\n"
    "   - Retorno: Trechos textuais das políticas violadas ou necessárias.\n\n"
    "2. [auditar_conformidade_regras]\n"
    "   - Descrição: Avalia se o comportamento relatado fere alguma norma de fóruns.\n"
    "   - Entrada: analise_do_agente (string).\n"
    "   - Retorno: String com o embasamento normativo direto para suporte legal."
)

AUDITOR_CARD_DESC = (
    "Responsável por extrair o embasamento normativo e buscar diretrizes da "
    "comunidade aplicáveis a comentários sinalizados como problemáticos."
)
