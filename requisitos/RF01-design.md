# Design - RF01: Chat interativo via CLI com agente OpenAI + AWS Strands

Referência: `requisitos/RF01-chat-cli-agente.md`

> Revisado após auditoria de segurança: sessão autenticada, dados externos
> reduzidos a um esquema validado e limites explícitos por turno.

## 1. Decisões de design
| ID | Decisão |
|----|---------|
| D1 | Linguagem: Python 3.11+; lock e ambiente validados em Windows/Python 3.14 |
| D2 | Configuração via arquivo `.env` (`python-dotenv`) |
| D3 | Framework de agente: AWS Strands Agents SDK (`strands-agents[openai]`) |
| D4 | `SecureSessionManager`, extensão do `FileSessionManager`, autentica registros e manifesto com HMAC-SHA256 |
| D5 | Tool `current_datetime` retorna data/hora atual em UTC |
| D5a | Tool `weather_forecast(city)` consulta a OpenWeatherMap (endpoints gratuitos `/data/2.5/weather` e `/data/2.5/forecast`, `units=metric`, `lang=pt_br`) via `urllib` (sem dependência nova) e retorna JSON com tempo atual e mín./máx. por dia |
| D6 | Modelo: OpenAI `gpt-4o-mini` (padrão), via `OpenAIModel` do Strands |
| D7 | Ao iniciar, o programa pergunta se continua a última sessão ou cria uma nova |
| D8 | Respostas em streaming, mantido do RF01 |

## 2. Arquitetura
```
Usuário (cmd)
   │  input
   ▼
main.py ── loop de chat
   │
   ├─► python-dotenv  → lê .env (OPENAI_API_KEY, OPENAI_MODEL_ID)
   │
   ├─► Agent (Strands)
   │      ├─ OpenAIModel  → API da OpenAI
   │      ├─ tools: [current_datetime, weather_forecast]
   │      ├─ hooks: TurnBudget
   │      └─ session_manager: SecureSessionManager
   │
   └─► sessions/verified-v1/ (histórico + manifesto autenticado por session_id)
```

## 3. Componentes

### 3.1 Configuração (`.env`)
| Variável | Obrigatória | Padrão |
|----------|-------------|--------|
| `OPENAI_API_KEY` | Sim | — |
| `OPENAI_MODEL_ID` | Não | `gpt-4o-mini` |
| `OPENWEATHER_API_KEY` | Para a tool de clima | — |
| `SESSION_STORAGE_DIR` | Não | `./sessions` |
| `SYSTEM_PROMPT` | Não | assistente prestativo em português |

### 3.2 Agente (Strands)
- `OpenAIModel(client_args={"api_key": ...}, model_id=os.getenv("OPENAI_MODEL_ID", "gpt-4o-mini"))`
- `Agent(model=..., tools=[current_datetime, weather_forecast], session_manager=..., hooks=[TurnBudget()], ...)`.
- Streaming passa por `stream_reply`: prazo global, tamanho máximo e filtro incremental ANSI/OSC.
- Prompt configurável recebe também regras de origem/confiança e limites de capacidade.
- Retries automáticos desabilitados; cliente OpenAI com timeout de 15 segundos por operação.

### 3.3 Memória de sessão em arquivo
- `SecureSessionManager` usa `SESSION_STORAGE_DIR/verified-v1`.
- `session_id` no formato `sessao-<UUIDv4>`; manifesto autentica hashes, caminhos e atividade.
- Ao iniciar: se existir sessão verificada, perguntar `Continuar última sessão verificada? [S/n]`:
  - **S** → reutiliza a sessão válida com atividade autenticada mais recente.
  - **N** → gera novo `session_id`; sessões antigas permanecem arquivadas.
- Diretório `sessions/` adicionado ao `.gitignore`.
- Chave local de 32 bytes em `%LOCALAPPDATA%/IaCafe/<hash-do-projeto>/session-key.bin`,
  cifrada com DPAPI no Windows. Diretórios privados com ACL; bloqueio de links/reparse points.
- Lock de arquivo impede dois processos de abrir a mesma sessão simultaneamente.
- Históricos antigos sem manifesto são preservados, sem migração automática.
- A assinatura detecta adulterações sem a chave, mas não protege contra processo
  malicioso rodando como o mesmo usuário, nem rollback completo de versão assinada.
- JSON continua legível: não há criptografia do conteúdo das conversas.

### 3.4 Tool `current_datetime`
```python
@tool
def current_datetime() -> str:
    """Retorna a data e hora atuais em UTC."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
```
- Sem parâmetros; retorna ISO 8601 com `+00:00` (ex.: `2026-11-07T14:32:10+00:00`).

### 3.5 Loop do chat
1. Banner inicial com instruções (`sair` para encerrar).
2. Prompt `Você: ` → lê entrada; vazia é ignorada.
3. `Agente: ` → consome `stream_async` e imprime tokens incrementalmente.
4. Encerra com `sair`/`exit`/`quit`, Ctrl+C ou Ctrl+D, sem traceback.

## 4. Estrutura de arquivos
```
projeto_ia_cafe/
├── requisitos/
│   ├── RF01-chat-cli-agente.md
│   └── RF01-design.md
├── main.py                 # agente + loop do chat
├── agent_safety.py         # limites e filtro de saída
├── weather_tools.py        # consultas e validação de clima
├── secure_sessions.py      # memória autenticada e chave local
├── requirements.in         # dependências diretas
├── requirements.lock       # versões transitivas e hashes
├── requirements.txt        # instalação com hashes obrigatórios
├── .env.example
├── .env                    # não versionado
├── .gitignore              # .env, sessions/, .venv/
├── sessions/               # gerado em runtime (histórico de sessões)
└── README.md
```

## 5. Tratamento de erros
| Cenário | Comportamento |
|---------|---------------|
| `OPENAI_API_KEY` ausente | Mensagem clara + exit ≠ 0 |
| Erro de API/rede | Mensagem amigável; o chat continua |
| Sessão sem assinatura/corrompida | Preserva arquivos, ignora na seleção e oferece sessão nova |
| Falha na abertura selecionada | Tenta um UUID novo; segunda falha termina com mensagem sanitizada |
| Falha de integridade durante conversa | Interrompe o chat; não continua usando estado suspeito |
| Nenhuma sessão anterior | Pula a pergunta de continuação |

## 6. Fluxo de execução
```
início
  → carrega .env → valida OPENAI_API_KEY
  → verifica manifestos das sessões novas
      ├─ existe válida → "Continuar última sessão verificada? [S/n]"
      └─ não existe → cria nova
  → instancia OpenAIModel + SecureSessionManager + Agent(tools, TurnBudget)
  → loop: Você → stream_async → Agente (resposta incremental)
  → sair → encerra
```

## 7. Critérios de aceite do design
1. Resposta a "Que dia é hoje?" usa a tool e retorna data UTC correta.
2. Ao encerrar e reabrir, escolher "S" mantém o contexto (agente lembra fatos da conversa anterior).
3. Escolher "N" inicia sessão nova e um novo diretório de sessão aparece em `sessions/`.
4. Streaming funciona com tool calls (a resposta final é exibida incrementalmente).
5. `pip install -r requirements.txt` + `python main.py` executam sem configuração extra além do `.env`.

## 8. Decisões tomadas nesta sessão
| Tema | Decisão |
|------|---------|
| Comportamento da sessão | Perguntar ao iniciar (continuar ou nova) |
| Fuso da tool | UTC |

## 9. Limites de segurança

| Recurso | Limite |
|---------|--------|
| Cidade | 100 caracteres; nome e país sem URL/comandos |
| Entrada do usuário | 4.000 caracteres |
| Corpo HTTP meteorológico | 256.000 bytes; redirects recusados |
| Chamada HTTP meteorológica | 5 segundos por operação; executada fora do event loop |
| Resposta do modelo | 800 tokens por chamada |
| Turno | 45 segundos, 4 chamadas de modelo, 4 tools, 12.000 caracteres de saída |
| Contexto | Janela de 20 mensagens e teto de 12.000 tokens projetados |
| Histórico | 2.000 registros, 256.000 bytes/registro e 16 MB/sessão |

A previsão conserva datas UTC. Texto de `description`, nomes de cidade/país e
`dt_txt` da resposta externa são ignorados; temperaturas, umidade, código e epoch
são validados. Condições meteorológicas são geradas por mapeamento local.
Os limites do cliente não substituem limites de gastos configurados no provedor.
