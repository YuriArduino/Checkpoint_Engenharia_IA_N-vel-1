## 📑 Manual de Arquitetura Multiagentes: Padrão Plug-and-Play (A2A v1.0 / MCP)

Este documento define o padrão arquitetural obrigatório para a criação, execução e acoplamento de novos agentes especialistas no ecossistema. Cada agente opera de forma isolada em seu próprio container Docker e deve, obrigatoriamente, expor três camadas bem definidas: server (Infraestrutura de Rede), executor (Tradução e Telemetria) e agent (Processamento Cognitivo / LLM).

       [ REDE INTERNA COMPOSE / MESH ]
                     │
                     ▼

┌────────────────────server.py─────────────────────┐
│ Expõe: │
│ ├─► /rpc (A2A / JSONRPC via Starlette) │
│ └─► /mcp (Capacidades Locais via FastMCP) │
└────────────────────┬─────────────────────────────┘
│ Payload Binário (Wire Format)
▼
┌──────────────────executor.py─────────────────────┐
│ 1. Trata nulos do context.message e Thread ID │
│ 2. Deserializa o payload e invoca o agente │
│ 3. Injeta Metadados de Telemetria de Suporte │
│ 4. Envelopa resposta usando o Enum do Protobuf │
└────────────────────┬─────────────────────────────┘
│ Dicionário Limpo (Pydantic Input)
▼
┌───────────────────agent/─────────────────────────┐
│ 1. Definição do Contrato de Saída (BaseModel) │
│ 2. Inicialização via factory 'create_agent' │
│ 3. Resposta Estruturada via pasada única │
└──────────────────────────────────────────────────┘

---

## ─── 📁 Camada 1: O Núcleo do Agente (agent/)

Responsável estritamente pela inteligência cognitiva, engenharia de prompt e inferência com o Modelo de Linguagem (LLM).

## Diretrizes de Implementação:

1.  Contrato de Saída Rígido: Todo agente deve definir um schema de saída utilizando pydantic.BaseModel. O modelo deve ser forçado a responder estritamente neste formato usando o método .with_structured_output(Schema) acoplado diretamente à instância da LLM.
2.  Inicialização v1.0: O agente deve ser construído utilizando a factory function unificada from langchain.agents import create_agent configurada com o parâmetro explícito system_prompt.
3.  Passada Única de Inferência: O prompt e as ferramentas associadas (via MultiServerMCPClient) devem ser desenhados para capturar todas as propriedades do domínio daquele agente em um único disparo cognitivo, evitando chamadas repetidas à API e desperdício de tokens.
4.  Isolamento de Estado: O agente opera de forma puramente funcional (stateless) perante o ecossistema. Ele processa o payload recebido e retorna o dado parseado na chave structured_response do dicionário gerado pelo ainvoke. A persistência macro de estados e barreiras de interrupção fica delegada ao orquestrador global.

---

## ─── ⚙️ Camada 2: O Tradutor (executor.py)

Atua como o intermediário (Data Mapper) entre o formato compacto de tráfego de rede (wire format) e a lógica em Python do agente. É aqui que a mágica da Telemetria de Retorno/Suporte é injetada.

## Diretrizes de Implementação:

1.  Herança Obrigatória: Deve herdar diretamente de a2a.server.agent_execution.AgentExecutor e implementar o método assíncrono execute(self, context: RequestContext, event_queue: EventQueue).
2.  Rastreabilidade de Sessão: Deve extrair o comentario_aluno e o context_id de dentro do RequestContext. Caso o context.message seja avaliado como nulo pelo PyLance, deve aplicar um guard defensivo gerando um identificador através de str(uuid.uuid4()).
3.  Consistência de Enums (A2A v1.0): A resposta entregue ao barramento de eventos deve, obrigatoriamente, utilizar o método a2a.helpers.new_text_message() associando explicitamente o Enum do descriptor do Protobuf: role=Role.ROLE_AGENT.
4.  Injeção de Metadados de Suporte: Antes de enfileirar o evento, o executor deve injetar metadados operacionais no atributo .metadata da mensagem (ex: agent_version, capability_domain, wire_format). Esses dados alimentam os painéis de observabilidade e permitem que o BFA monitore em tempo real a eficácia do Broker.
5.  Tratamento de Linhas: Seguir à risca o limite de 100 caracteres exigido pelo formatador Black, quebrando blocos longos de lógica ternária ou strings de erro.

---

## ─── 🌐 Camada 3: A Fachada de Rede (server.py)

Responsável por ligar o container à rede interna do Docker Compose (ia-mesh) e expor as portas de comunicação unificadas. É o coração do Federated MCP Isolation.

## Diretrizes de Implementação:

1.  Duplicidade de Servidores: O arquivo utiliza o framework Starlette para unificar dois endpoints críticos sob o mesmo ciclo de vida ASGI:

- Endpoint A2A (/rpc): Gerado automaticamente via factory create_jsonrpc_routes, escuta requisições estruturadas vindas do Orquestrador.
  - Endpoint MCP Nativo (/mcp): Gerado pelo servidor local FastMCP, expõe e gerencia de forma autônoma os recursos internos (como arquivos locais) e ferramentas do domínio do agente. O aplicativo ASGI do FastMCP deve ser acoplado à fachada principal usando app.mount("/mcp", mcp_asgi).

2.  Contrato de Autodescoberta (AgentCard): Deve instanciar um AgentCard v1.0 rico detalhando o domínio semântico do agente através de micro-funções descritivas em skills e tags (ex: [analisar_sentimento], [detectar_problemas]).
3.  Mapeamento de Interfaces: O AgentCard não possui URL global fixa. Ele deve documentar explicitamente a lista supported_interfaces contendo os dois caminhos de rede internos do container Docker:

- protocol_binding="JSONRPC" apontando para a rota /rpc.
  - protocol_binding="MCP_HTTP" apontando para a rota /mcp.

---

## ⚓ Como o Ecossistema Reage ao PnP de um Novo Agente?

Quando você adiciona uma nova pasta seguindo esse padrão e dá um docker-compose up:

1.  O BFA (Broker) varre o endpoint de Card do novo agente, lê a interface "MCP_HTTP" e dá um list_tools() nativo no /mcp dele. Os metadados ricas e as capacidades do novo agente são automaticamente salvos na tabela SQL e indexados no FAISS + BM25 RRF sem que você precise reescrever uma única linha de código no BFA.
2.  O Orquestrador (LangGraph) descobre o endereço do novo agente perguntando ao BFA e passa a chamá-lo via gRPC/A2A de forma dinâmica. O reduce_messages garante que o histórico trafegado entre eles seja comprimido de forma invisível.
3.  A Persistência flui de forma limpa, já que os Enums binários do Protobuf são devidamente traduzidos para strings legíveis no banco SQLite do MVP, permitindo auditorias perfeitas.
