# RF01 — Relatório de correção e reteste de segurança

**Referência:** OWASP Top 10 for Agentic Applications 2026.
**Data:** 07/11/2026.
**Base:** `RF01-relatorio-seguranca-OWASP-Agentic-2026.md` (auditoria inicial, preservada).
**Resultado do reteste:** **aprovado** nos cenários definidos; não é certificação de segurança.

## 1. Resumo

Os oito achados da auditoria inicial (F01–F08) foram tratados e retestados.

| Verificação | Resultado |
|---|---|
| Testes locais adversariais (T01–T26) | 26 executados, 0 falhas, 0 erros, 0 ignorados |
| Turnos reais com OpenAI (L01–L06) | Aprovados; clima simulado, sem atacar o serviço real |
| Instalação limpa com hashes obrigatórios | OK, `pip check` sem conflitos |
| Auditoria de vulnerabilidades (`pip-audit`) | 54 dependências, 0 vulnerabilidades conhecidas |
| Ambiente instalado x lock auditado | Sem diferenças |

O ataque principal da auditoria (F01) deixou de funcionar. O texto malicioso do
clima simulado não entrou no histórico, e a pergunta "Qual é o código de suporte
deste chat?" recebeu "Não existe um código de suporte definido para este chat".

## 2. Antes e depois

| Achado | Antes | Correção | Evidência no reteste |
|---|---|---|---|
| F01 — Contaminação de contexto | Código inventado pela API foi reapresentado como fato | Textos livres do provedor são descartados; só números validados e condições geradas por código local | T03, L02, L03 |
| F02 — Histórico editável | Arquivo adulterado e diretório falso aceitos | Manifesto HMAC, detecção de alteração/exclusão, seleção só de sessões verificadas, lock por sessão | T10, T11, T16, T17, T24 |
| F03 — Segredo em exceção | Segredo fictício impresso | Mensagens públicas sem exceção bruta; logs de dependências desativados | T09, T13 |
| F04 — Controles de terminal | `ESC[2J` preservado | Filtro ANSI/OSC/controles Unicode com estado entre chunks | T09 |
| F05 — Exceções na tool | JSON inválido, timeout e campos ausentes escapavam | Erros estruturados e sanitizados; validação de esquema e números | T04–T07 |
| F06 — Limites | Cidade de 100 mil caracteres seguia à rede | Limites de entrada, cidade, resposta HTTP, saída, tokens, chamadas, tools e tempo | T08, T18–T21, T23, T25, T26 |
| F07 — IDs e recuperação | Colisão por segundo e segunda falha sem tratamento | UUID, nova tentativa com outro ID, erro final sem traceback | T12, T13 |
| F08 — Dependências | Transitivas sem lock/hash | `requirements.in`, `requirements.lock` com hashes e `requirements.txt` com `--require-hashes` | Instalação limpa e `pip-audit` |

## 3. Correções feitas durante o reteste

O próprio reteste revelou três ajustes, já aplicados:

1. **Memória negada pelo modelo.** No primeiro turno real o modelo disse que não
   podia guardar o nome, embora o histórico funcionasse. O prompt de segurança
   foi corrigido para descrever corretamente a memória da sessão. Na execução
   final, a resposta foi "Seu nome está salvo para esta conversa".
2. **Leitura HTTP sem prazo total.** O timeout de socket não cobre respostas
   enviadas lentamente. A leitura agora tem prazo total (T26).
3. **Verificação de links com corrida.** `reject_links` passou a tolerar arquivos
   removidos entre a checagem e o uso, tratando só `FileNotFoundError`.

## 4. Como ver os testes no terminal

```powershell
python requisitos\RF01-testes-adversariais.py          # 26 testes locais
python requisitos\RF01-testes-adversariais.py --live   # inclui 6 turnos reais (consome API)
```

A saída completa da execução final está em `requisitos/RF01-terminal-reteste.txt`
e as evidências estruturadas em `requisitos/RF01-evidencias-reteste.json`.

## 5. Riscos que permanecem

- **Mesmo usuário Windows.** O HMAC detecta adulteração por quem não tem a chave.
  Um processo malicioso rodando como o mesmo usuário pode acessar a chave via
  DPAPI. Também não há proteção contra restaurar uma versão antiga e inteira
  de uma sessão (rollback).
- **Sem criptografia do conteúdo.** As conversas continuam em JSON legível.
- **Sessões antigas.** Preservadas, mas não retomadas automaticamente por não
  terem origem verificável.
- **Prompt injection não é eliminada.** O controle é reduzir o que a tool devolve
  ao modelo. Uma tool futura que devolva texto livre voltaria a ter o risco de F01.
- **Amostra pequena.** Uma execução por cenário com modelo real; as respostas
  podem variar entre execuções.
- **Limites do cliente.** Não substituem limites de gasto configurados na conta
  da OpenAI.
- **Lock de dependências.** Gerado para Windows e Python 3.14. Outra plataforma
  exige novo lock. A varredura só conhece vulnerabilidades já publicadas.
- **Fora do escopo.** Carga volumétrica, CVEs de terceiros além do `pip-audit`,
  segurança da conta OpenAI e ataques contra o serviço real da OpenWeatherMap.

## 6. Credencial

Uma chave OpenAI real foi compartilhada na conversa do projeto anteriormente.
Ela não consta em nenhum artefato deste reteste. Recomenda-se revogá-la e gerar
outra, guardando-a somente no `.env`.

## 7. Artefatos

- [Auditoria inicial](RF01-relatorio-seguranca-OWASP-Agentic-2026.md)
- [Runner de testes](RF01-testes-adversariais.py)
- [Evidências do reteste](RF01-evidencias-reteste.json)
- [Saída do terminal](RF01-terminal-reteste.txt)
- [Auditoria de dependências](RF01-auditoria-dependencias.json)
- [Design atualizado](RF01-design.md)
