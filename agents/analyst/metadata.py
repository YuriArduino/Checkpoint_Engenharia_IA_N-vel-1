"""Metadados e descrições semânticas do Agente Analista (Analyst Agent)."""

ANALYST_SKILL_DESC = (
    "Especialista em processamento semântico e triagem comportamental de interações.\n\n"
    "CAPACIDADES COGNITIVAS MAPEADAS:\n"
    "1. [analisar_sentimento_comentario]\n"
    "   - Descrição: Classifica o tom geral do texto em categorias específicas.\n"
    "   - Entrada: texto_comentario (string).\n"
    "   - Retorno: 'positivo', 'neutro' ou 'problematico'.\n\n"
    "2. [detectar_problemas_comentario]\n"
    "   - Descrição: Identifica problemas potenciais como spam, ofensas ou bugs.\n"
    "   - Entrada: texto_comentario (string).\n"
    "   - Retorno: Lista de strings com problemas mapeados ou lista vazia.\n\n"
    "3. [extrair_tom_e_contexto]\n"
    "   - Descrição: Analisa a urgência e emoções secundárias para priorização.\n"
    "   - Entrada: texto_comentario (string).\n"
    "   - Retorno: JSON contendo nível de urgência (alta/media/baixa) e tags de sentimento."
)

ANALYST_CARD_DESC = (
    "Responsável por classificar comentários em positivo, neutro ou problemático, "
    "fornecendo contexto semântico detalhado para a esteira de moderação."
)
