"""Wrapper do agente de análise semântica e comportamental (Analyst Agent)."""

import json
import logging
import uuid

from a2a.helpers import new_text_message
from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import Role, UnsupportedOperationError

from .agent.commentary_analysis import run_analyst_agent

logger = logging.getLogger("a2a.commentary_analysis_executor")


class CommentaryAnalysisExecutor(AgentExecutor):
    """Executor do agente especialista em análise de comentários."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        logger.info("agent.execute.commentary_analysis")

        # 2. Rastreabilidade de Sessão
        comentario_aluno = context.get_user_input()
        msg = context.message

        # Guard defensivo para garantir thread_id válido
        thread_id = msg.context_id if msg is not None and msg.context_id else str(uuid.uuid4())

        logger.info("thread_id processado: %s", thread_id)

        try:
            result_dict = await run_analyst_agent(comentario_original=comentario_aluno)
        except RuntimeError as e:
            logger.error("Falha cognitiva ou de rede no agente: %s", e)
            result_dict = None

        if not result_dict:
            desc_erro = "Falha interna. Comentário classificado como neutro por segurança."
            result_dict = {
                "classificacao": "neutro",
                "analise_do_agente": desc_erro,
            }

        response_payload = json.dumps({"structured_response": result_dict}, ensure_ascii=False)

        # 3. Consistência de Enums (A2A v1.0)
        agent_message = new_text_message(
            str(response_payload),
            role=Role.ROLE_AGENT,
        )

        # 4. Injeção de Metadados de Suporte (RESOLVIDO: Atribuição em Protobuf Struct)
        agent_message.metadata.update(
            {
                "agent_version": "1.0.0",
                "capability_domain": "commentary_analysis",
                "wire_format": "application/json",
                "trace_id": thread_id,
            }
        )

        await event_queue.enqueue_event(agent_message)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        logger.info("agent.cancel.commentary_analysis")
        raise UnsupportedOperationError("Cancelamento não suportado nesta versão.")
