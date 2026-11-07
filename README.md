# Chat IA Café

Chat interativo de terminal com agente **AWS Strands** + modelo **OpenAI** (`gpt-4o-mini`),
memória de sessão em arquivo local e tools de data/hora e previsão do tempo (UTC).

Requisitos: `requisitos/RF01-chat-cli-agente.md` · Design: `requisitos/RF01-design.md`

## Setup (Windows, Python 3.11+)

```cmd
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
if not exist .env copy .env.example .env
```

Edite o `.env` e preencha `OPENAI_API_KEY`.

| Variável | Obrigatória | Padrão |
|----------|-------------|--------|
| `OPENAI_API_KEY` | Sim | — |
| `OPENAI_MODEL_ID` | Não | `gpt-4o-mini` |
| `OPENWEATHER_API_KEY` | Para a tool de clima | — (gratuita em openweathermap.org) |
| `SESSION_STORAGE_DIR` | Não | `./sessions` |
| `SYSTEM_PROMPT` | Não | Assistente prestativo em português |

## Execução

```cmd
python main.py
```

> As dependências também estão instaladas no Python do sistema (`pip install --user -r requirements.txt`),
> então não é preciso ativar o venv. Se `python` abrir a Microsoft Store, abra um terminal novo
> ou use `.\.venv\Scripts\python.exe main.py`.

- Se houver sessão verificada anterior, o programa pergunta `Continuar última sessão verificada? [S/n]`.
- Encerre com `sair`, `exit`, `quit` ou Ctrl+C.
- O histórico novo fica em `sessions/verified-v1/session_<id>/` (não versionado).

## Proteções e histórico

- As sessões usam UUID e manifesto assinado. Arquivos adulterados, removidos ou
  sem assinatura não são retomados. As sessões antigas continuam no disco,
  mas não são importadas automaticamente, pois não é possível verificar sua origem.
- A chave de assinatura é criada automaticamente fora do projeto, em
  `%LOCALAPPDATA%\IaCafe\<identificador-do-projeto>\session-key.bin`, protegida
  por DPAPI para o usuário Windows. As pastas de chave e sessões verificadas
  recebem ACL restrita. Não é necessário configurar outra chave no `.env`.
- As mensagens continuam em JSON legível; assinatura não é criptografia.
  Não apague a chave local se precisar retomar as sessões. Outro usuário/máquina
  não consegue reutilizá-la diretamente.
- O clima contém somente números validados e condições geradas por códigos
  conhecidos. Textos livres do provedor são descartados.
- O chat limita entradas a 4.000 caracteres e cada turno a 45 segundos,
  quatro chamadas de modelo, quatro tools e 800 tokens por resposta do modelo.
  Há ainda limite de contexto estimado, saída e tamanho do histórico.
- Falhas são exibidas sem exceções brutas. Sequências de controle do terminal
  são removidas, inclusive quando chegam fragmentadas.

## Testes de segurança visíveis no terminal

```powershell
python requisitos\RF01-testes-adversariais.py
python requisitos\RF01-testes-adversariais.py --live
```

O primeiro comando não usa serviços externos. O segundo também exibe perguntas
e respostas de seis turnos com OpenAI (consome API), usando clima simulado.
Os dois usam sessões temporárias. O resultado fica em
`requisitos/RF01-evidencias-reteste.json`; a auditoria inicial é preservada.

## Dependências reproduzíveis

`requirements.in` contém as dependências diretas; `requirements.lock` fixa
também as transitivas e seus hashes. `requirements.txt` exige esses hashes.
O lock atual foi produzido para Windows/Python 3.14; em outra plataforma,
gere e valide um lock específico.

Para atualizar deliberadamente (em ambiente de manutenção com `pip-tools` e
`pip-audit` instalados):

```powershell
pip-compile --generate-hashes --strip-extras --output-file requirements.lock requirements.in
pip-audit -r requirements.lock --disable-pip --no-deps
```

Revise o diff do lock e rode os testes antes de adotar atualizações.
