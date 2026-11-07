# RF01 - Chat interativo via CLI com agente OpenAI + AWS Strands

## 1. Descrição
Aplicação em Python, executada localmente via terminal (cmd), que oferece um chat interativo com um agente de IA simples, construído com o **AWS Strands Agents SDK** e usando um modelo da **OpenAI**.

## 2. Objetivo
Permitir ao usuário conversar com um LLM pelo terminal, com histórico da sessão e respostas em streaming, servindo como base simples para evoluções futuras.

## 3. Escopo
**Dentro do escopo**
- Chat em loop no terminal.
- Agente único com duas tools: data/hora atual (UTC) e previsão do tempo (OpenWeatherMap).
- Memória de sessão persistida em arquivo local, com opção de retomar a última sessão.
- Resposta exibida em streaming (token a token).
- Configuração via arquivo `.env`.

**Fora do escopo**
- RAG, multi-agentes e demais tools além de data/hora e previsão do tempo.
- Interface web/gráfica.
- Deploy em nuvem (AWS ou outro); execução apenas local.

## 4. Requisitos funcionais
| ID | Descrição |
|----|-----------|
| RF01.1 | Ao iniciar, o programa exibe uma mensagem de boas-vindas e instruções (como sair). |
| RF01.2 | O programa lê continuamente a entrada do usuário (prompt `Você: `). |
| RF01.3 | Cada mensagem é enviada ao agente Strands, que usa o modelo OpenAI configurado. |
| RF01.4 | A resposta do agente é exibida em streaming no terminal (prompt `Agente: `). |
| RF01.5 | O agente mantém o contexto das mensagens anteriores, com histórico persistido em arquivos locais (diretório de sessões). |
| RF01.5a | Ao iniciar com sessão anterior existente, o programa pergunta se o usuário deseja continuar a última sessão (contexto restaurado) ou começar uma nova. |
| RF01.5b | O agente possui a tool `current_datetime`, que retorna a data e hora atuais em UTC; perguntas sobre data/hora devem ser respondidas com base nela. |
| RF01.5c | O agente possui a tool `weather_forecast(city)`, que consulta a OpenWeatherMap e retorna o tempo atual (temperatura, sensação, umidade, condição) e a previsão dos próximos 5 dias (mín./máx. e condição por dia, em °C e português). Cidade inexistente, chave ausente ou falha de rede retornam mensagem de erro, sem derrubar o chat. |
| RF01.6 | Entradas vazias são ignoradas. |
| RF01.7 | O usuário encerra com `sair`, `exit` ou `quit`, ou com Ctrl+C / Ctrl+D, sem exibir stack trace. |
| RF01.8 | O agente possui um system prompt simples e configurável (ex.: assistente prestativo, responde em português). |
| RF01.9 | A interação é uma conversa em turnos: cada turno é composto por uma mensagem do usuário (`Você:`) seguida da resposta do agente (`Agente:`), sempre nessa ordem e visualmente distintos no terminal. |
| RF01.10 | O próximo turno só é solicitado após a resposta do agente terminar de ser exibida. |

## 5. Requisitos de configuração
| ID | Descrição |
|----|-----------|
| RC01 | `OPENAI_API_KEY` lida de arquivo `.env` (via `python-dotenv`). |
| RC02 | `OPENAI_MODEL_ID` opcional no `.env`; padrão `gpt-4o-mini`. |
| RC02c | `OPENWEATHER_API_KEY` no `.env` (chave gratuita em openweathermap.org); sem ela, a tool de clima informa que não está configurada. |
| RC02a | `SESSION_STORAGE_DIR` opcional no `.env`; padrão `./sessions`. Diretório no `.gitignore`. |
| RC02b | `SYSTEM_PROMPT` opcional no `.env`; padrão: assistente prestativo em português. |
| RC03 | Fornecer `.env.example` sem segredos; `.env` deve estar no `.gitignore`. |
| RC04 | Se a API key estiver ausente, exibir mensagem clara e encerrar com código ≠ 0. |

## 6. Requisitos não funcionais
- **Linguagem/versão:** Python 3.11+ (prazo assíncrono por turno); ambiente validado em Python 3.14 no Windows.
- **Execução:** local, Windows (cmd/PowerShell), `python main.py`.
- **Dependências:** `strands-agents[openai]`, `python-dotenv` (listadas em `requirements.txt`); uso de ambiente virtual recomendado.
- **Simplicidade:** `main.py` como entrada, com módulos separados para tools meteorológicas, proteções do agente e sessões autenticadas.
- **Tratamento de erros:** falhas de API/rede exibem mensagem amigável e o chat continua.
- **Segurança:** a API key nunca é impressa nem commitada.
- **Encoding:** suporte a UTF-8 (acentos) no terminal.

## 7. Estrutura sugerida
```
projeto_ia_cafe/
├── requisitos/
│   ├── RF01-chat-cli-agente.md
│   └── RF01-design.md
├── main.py
├── requirements.txt
├── .env.example
├── .gitignore
├── sessions/     (histórico de sessões, gerado em runtime)
└── README.md     (instruções de setup e execução)
```

## 8. Critérios de aceite
1. `pip install -r requirements.txt` conclui sem erro no ambiente Windows/Python 3.14 do lock validado; runtime exige Python 3.11+.
2. Com `.env` válido, `python main.py` abre o chat.
3. Enviar "Meu nome é Ana" e depois "Qual é o meu nome?" resulta em resposta contendo "Ana" (memória).
4. A resposta aparece de forma incremental (streaming).
5. `sair` encerra o programa limpamente; Ctrl+C também, sem traceback.
6. Sem `OPENAI_API_KEY`, o programa informa o erro e encerra.
7. Entrada vazia não gera chamada ao modelo.
8. Cada mensagem do usuário é sempre seguida de uma resposta do agente, formando turnos pergunta/resposta, e o prompt só reaparece após o fim da resposta.
9. "Que dia é hoje?" é respondida usando a tool com a data UTC correta.
10. Ao reabrir e escolher continuar a última sessão, o agente lembra fatos ditos anteriormente; escolher nova sessão cria um novo diretório em `sessions/`.
11. "Qual a previsão do tempo em São Paulo?" retorna temperatura atual e previsão dos próximos dias via OpenWeatherMap.

## 9. Premissas e riscos
- Usuário possui conta e chave válida da OpenAI com créditos.
- Strands não exige credenciais AWS ao usar o provedor OpenAI.
- Custos de API são de responsabilidade do usuário (gpt-4o-mini é de baixo custo).

## 10. Decisões tomadas
| Tema | Decisão |
|------|---------|
| Modelo | `gpt-4o-mini` (padrão, sobrescrevível via `.env`) |
| Tools | `current_datetime` (data/hora em UTC), `weather_forecast` (OpenWeatherMap, endpoints gratuitos `weather` e `forecast`) |
| Memória/Streaming | Sessão persistida em arquivo + streaming; ao iniciar, pergunta se continua a última sessão |
| API key | Arquivo `.env` |

## 11. Pontos em aberto (opcionais)
- Idioma do system prompt (sugerido: português).
- Persona/tema do agente (o projeto se chama "ia_cafe"; pode ser um assistente sobre café?).

## 12. Requisitos de segurança após auditoria OWASP Agentic 2026

| ID | Requisito |
|----|-----------|
| RS01 | Descartar textos livres da API meteorológica; validar valores e construir descrições locais por código. Não persistir instruções externas dessa API. |
| RS02 | Autenticar o histórico por manifesto HMAC, detectar alterações/exclusões, recusar arquivos sem assinatura e impedir abertura simultânea da mesma sessão. |
| RS03 | Manter a chave de integridade fora do histórico, protegida por DPAPI e ACL no Windows; preservar sessões antigas sem retomá-las automaticamente. |
| RS04 | Usar UUID nas sessões novas, selecionar por atividade autenticada e tratar falhas da primeira abertura e do fallback sem traceback. |
| RS05 | Exibir erros públicos sem segredos ou exceções brutas e filtrar controles do terminal em streaming. |
| RS06 | Limitar tamanho de cidade, entrada, resposta HTTP, saída, contexto, arquivos de sessão e número/tempo de chamadas por turno. |
| RS07 | Instalar dependências travadas com hashes e auditar vulnerabilidades conhecidas antes de atualizações. |
| RS08 | Executar regressão adversarial local e validar retomada/contaminação de memória com modelo real antes de fechar as correções. |

Os detalhes e valores dos limites estão no design e no relatório de reteste.
