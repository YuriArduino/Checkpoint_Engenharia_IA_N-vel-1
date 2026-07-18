"""Wrapper do agente pesquisador de políticas (Auditor Agent)."""

import json
import logging
import uuid

from a2a.helpers import new_text_message
from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import Role, UnsupportedOperationError

from .agent.policy_audit import run_researcher_agent

logger = logging.getLogger("a2a.policy_audit_executor")


class PolicyAuditExecutor(AgentExecutor):
    """Executor do agente especialista em pesquisa de políticas."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        logger.info("agent.execute.policy_audit")

        # Recupera o payload JSON enviado pelo Analista (via Orquestrador)
        payload_str = context.get_user_input()

        # 2. Rastreabilidade de Sessão (Guard defensivo de 100 caracteres)
        msg = context.message
        thread_id = msg.context_id if msg is not None and msg.context_id else str(uuid.uuid4())

        logger.info("thread_id resolvido para auditoria: %s", thread_id)

        # Faz o parse do JSON recebido do agente anterior
        try:
            dados_analista = json.loads(payload_str)

            # Se vier envelopado pelo orquestrador na chave global de contrato
            if "structured_response" in dados_analista:
                dados_analista = dados_analista["structured_response"]

            classificacao = dados_analista.get("classificacao", "neutro")
            analise_do_agente = dados_analista.get("analise_do_agente", "Análise indisponível.")
        except json.JSONDecodeError:
            logger.error("Falha ao decodificar payload do analista: %s", payload_str)
            classificacao = "neutro"
            analise_do_agente = "Erro na leitura dos dados."

        # Dispara a inteligência do agente (Isolamento de Estado / Sem thread_id)
        try:
            result_dict = await run_researcher_agent(
                classificacao=classificacao, analise_do_agente=analise_do_agente
            )
        except RuntimeError as e:  # RESOLVIDO: W0718 Broad Exception mitigado
            logger.error("Falha cognitiva ou de rede no agente: %s", e)
            result_dict = None

        if not result_dict:
            # Mantém a assinatura 'structured_response' exigida pela arquitetura v1.0
            desc_erro = "Nenhuma política necessária por falha interna."
            result_dict = {
                "structured_response": {
                    "politicas_relevantes": desc_erro,
                }
            }

        # Serializa o payload estruturado em formato string/JSON para trafegar via A2A
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
                "capability_domain": "policy_audit",
                "wire_format": "application/json",
                "trace_id": thread_id,
            }
        )

        # Despacha o evento
        await event_queue.enqueue_event(agent_message)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        logger.info("agent.cancel.policy_audit")
        raise UnsupportedOperationError("Cancelamento de auditoria não suportado.")
