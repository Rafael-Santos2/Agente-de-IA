# Plano de Implementação - RF01: Chat CLI com Agente OpenAI + AWS Strands

> Plano original preservado. A etapa adicional de segurança está descrita ao
> final; seus testes e controles substituem as simplificações iniciais do plano.

Referências:
- Funcional: `requisitos/RF01-chat-cli-agente.md`
- Design: `requisitos/RF01-design.md`

## 1. Visão geral

Implementação de um chat de terminal em Python com agente AWS Strands, modelo
OpenAI `gpt-4o-mini`, memória de sessão em arquivos locais, streaming e uma tool
de data/hora UTC. Solução pequena: um único `main.py`, sem testes automatizados
obrigatórios, com validação via checklist manual (critérios de aceite).

## 2. Papéis (agentes) necessários

| Papel | Responsabilidade | Quem executa |
|-------|------------------|--------------|
| **Dev** | Implementa o código conforme o design | Agente Devin / desenvolvedor |
| **Tech Lead (revisor)** | Revisa código contra o design, aprova critérios de aceite | Usuário (ou Devin em revisão) |
| **Usuário (product owner)** | Fornece `OPENAI_API_KEY`, valida o chat de ponta a ponta | Usuário |
| **Agente de runtime** | O próprio agente Strands em execução (não é um papel humano) | Código |

> Por se tratar de solução pequena, uma única implementação cobre as tarefas de
> Dev; o Tech Lead faz acompanhamento pela checklist da seção 6.

## 3. Tarefas de implementação

### Fase 0 - Preparação do ambiente (usuário)
| # | Tarefa | Responsável | Critério |
|---|--------|-------------|----------|
| 0.1 | Verificar Python 3.10+ instalado (`python --version`) | Usuário | Versão OK |
| 0.2 | Obter `OPENAI_API_KEY` válida com créditos | Usuário | Chave em mãos |

### Fase 1 - Base do projeto (Dev)
| # | Tarefa | Detalhe | Depende de |
|---|--------|---------|-----------|
| 1.1 | Criar `.venv` e `requirements.txt` | Deps: `strands-agents[openai]`, `python-dotenv` | 0.1 |
| 1.2 | Criar `.env.example` e `.gitignore` | `.env.example` lista as 4 variáveis sem valores; `.gitignore` ignora `.env`, `sessions/`, `.venv/` | — |
| 1.3 | Criar `.env` local | Copiar do `.env.example` + preencher a key | 1.2, 0.2 |
| 1.4 | Instalar dependências | `pip install -r requirements.txt` | 1.1 |

### Fase 2 - Implementação do `main.py` (Dev)
| # | Tarefa | Detalhe | Depende de |
|---|--------|---------|-----------|
| 2.1 | Carregar config | `load_dotenv()`, ler `OPENAI_API_KEY` (obrigatória), `OPENAI_MODEL_ID`, `SESSION_STORAGE_DIR`, `SYSTEM_PROMPT` | 1.4 |
| 2.2 | Tool `current_datetime` | `@tool` retornando ISO 8601 em UTC | — |
| 2.3 | Seleção de sessão | Listar sessões em `SESSION_STORAGE_DIR`; se existir, perguntar "Continuar última sessão? [S/n]"; senão, criar `sessao-YYYYMMDD-HHMMSS` | 2.1 |
| 2.4 | Montar o agente | `OpenAIModel` + `Agent(tools=[...], session_manager=FileSessionManager, system_prompt)` | 2.1–2.3 |
| 2.5 | Loop do chat | Banner, `Você: `, `stream_async` com saída incremental `Agente: `, comandos `sair`/`exit`/`quit`, Ctrl+C/Ctrl+D sem traceback, entrada vazia ignorada | 2.4 |
| 2.6 | Tratamento de erros | Key ausente → msg + exit ≠ 0; erro de API/rede → msg amigável e continua; `sessions/` corrompido → aviso + nova sessão | 2.5 |

### Fase 3 - Documentação e validação (Dev + Usuário)
| # | Tarefa | Detalhe | Depende de |
|---|--------|---------|-----------|
| 3.1 | `README.md` | Setup (venv, pip install, .env) e execução (`python main.py`) | 2.x |
| 3.2 | Checklist de aceite | Executar os 10 critérios de aceite do RF01 + 5 do design | 2.6, 0.2 |
| 3.3 | Revisão final | Tech Lead revisa `main.py` contra o design | 3.2 |

## 4. Plano de acompanhamento

- **Rastreamento**: marcar cada critério de aceite como ✅/❌ durante a validação; qualquer ❌ vira bug a corrigir antes de fechar.
- **Revisão de código**: conferir (a) nenhuma key hardcoded ou logada, (b) streaming real (não print único), (c) tool com docstring clara, (d) pergunta de sessão só aparece quando há sessão anterior.
- **Riscos e mitigações**:

| Risco | Mitigação |
|-------|-----------|
| API key inválida/sem crédito | Fase 0 valida antes de codar; erro claro na execução |
| Versão do Strands muda API | Fixar versão no `requirements.txt` após validar |
| `sessions/` commitado por engano | `.gitignore` na tarefa 1.2 |
| Streaming não funciona no cmd do Windows | Validar no critério 4; fallback: imprimir resposta completa |

## 5. Ordem de execução (sequência resumida)

```
0.1 → 0.2 → 1.1 → 1.2 → 1.3 → 1.4
          → 2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 2.6
          → 3.1 → 3.2 → 3.3
```

## 6. Definition of Done

1. `python main.py` abre o chat com banner.
2. Todos os critérios de aceite do RF01 (1–10) e do design (1–5) passam no checklist.
3. `.env` e `sessions/` não são versionados.
4. `README.md` permite que outra pessoa execute o chat do zero.

## 7. Etapa adicional — correções de segurança

1. Separar validação meteorológica, limites do agente e autenticação de sessões.
2. Implementar controles RS01–RS07 do RF01, sem apagar históricos existentes.
3. Travar dependências transitivas e hashes; auditar a resolução instalada.
4. Rodar a regressão adversarial, com casos locais isolados e seis turnos reais
   apresentados no terminal.
5. Registrar comparação com a auditoria inicial, evidências e limites residuais
   em `RF01-relatorio-reteste-seguranca.md`.

Responsáveis sugeridos: desenvolvimento Python implementa, segurança revisa os
testes e o Tech Lead acompanha os critérios de fechamento. A etapa só fecha
com evidências de execução; exit code zero do chat, isoladamente, não basta.
