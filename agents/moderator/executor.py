"""Wrapper do agente revisor de decisões (Moderator Agent)."""

import json
import logging
import uuid

from a2a.helpers import new_text_message
from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import Role, UnsupportedOperationError

from .agent.decision_moderation import run_revisor_agent

logger = logging.getLogger("a2a.decision_moderation_executor")


class DecisionModerationExecutor(AgentExecutor):
    """Executor do agente especialista em recomendação de moderação."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        logger.info("agent.execute.decision_moderation")

        # Recupera o payload consolidado montado pelo Orquestrador
        payload_str = context.get_user_input()

        # 2. Rastreabilidade de Sessão (Guard defensivo de 100 caracteres)
        msg = context.message
        thread_id = msg.context_id if msg is not None and msg.context_id else str(uuid.uuid4())

        logger.info("thread_id resolvido para revisão: %s", thread_id)

        # Faz o parse do JSON contendo os dados do Analista e do Auditor
        try:
            dados_consolidados = json.loads(payload_str)

            # Se vier envelopado pelo orquestrador na chave de contrato
            if "structured_response" in dados_consolidados:
                dados_consolidados = dados_consolidados["structured_response"]

            analise_do_agente = dados_consolidados.get(
                "analise_do_agente", "Análise não informada."
            )
            politicas_relevantes = dados_consolidados.get(
                "politicas_relevantes", "Políticas não informadas."
            )
        except json.JSONDecodeError:
            logger.error("Falha ao decodificar payload consolidado: %s", payload_str)
            analise_do_agente = "Erro na leitura dos dados."
            politicas_relevantes = "Erro na leitura dos dados."

        # Dispara a inteligência do agente revisor (Isolamento de Estado / Sem thread_id)
        try:
            result_dict = await run_revisor_agent(
                analise_do_agente=analise_do_agente,
                politicas_relevantes=politicas_relevantes,
            )
        except RuntimeError as e:  # RESOLVIDO: W0718 Broad Exception mitigado
            logger.error("Falha cognitiva ou de rede no agente: %s", e)
            result_dict = None

        if not result_dict:
            # Mantém a assinatura 'structured_response' exigida pela arquitetura v1.0
            result_dict = {
                "structured_response": {
                    "recomendacao_acao": "Necessita de Revisão Humana",
                    "justificativa": "Falha na comunicação interna dos agentes.",
                }
            }

        # Serializa o payload estruturado
        response_payload = json.dumps(result_dict, ensure_ascii=False)

        # 3. Consistência de Enums (A2A v1.0)
        agent_message = new_text_message(
            str(response_payload),
            role=Role.ROLE_AGENT,
        )

        # 4. Injeção de Metadados de Suporte (RESOLVIDO: Atribuição em Protobuf Struct)
        agent_message.metadata.update(
            {
                "agent_version": "1.0.0",
                "capability_domain": "decision_moderation",
                "wire_format": "application/json",
                "trace_id": thread_id,
            }
        )

        # Despacha o evento
        await event_queue.enqueue_event(agent_message)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        logger.info("agent.cancel.decision_moderation")
        raise UnsupportedOperationError("Cancelamento de revisão não suportado.")
