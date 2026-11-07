import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from strands import Agent
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands.models.openai import OpenAIModel

from agent_safety import (
    BudgetExceeded, MAX_INPUT_CHARS, MAX_OUTPUT_CHARS, MAX_OUTPUT_TOKENS,
    SAFETY_PROMPT, TURN_TIMEOUT, TerminalFilter, TurnBudget, configure_logging, public_error,
)
from secure_sessions import (
    IntegrityError, SecureSessionManager, load_signing_key, new_session_id,
    private_directory, verified_sessions,
)
from weather_tools import current_datetime, weather_forecast

ROOT = Path(__file__).resolve().parent
EXIT_COMMANDS = {"sair", "exit", "quit"}
DEFAULT_PROMPT = "Você é um assistente prestativo. Responda sempre em português."


def choose_session_id(storage_dir, key):
    sessions, ignored = verified_sessions(storage_dir, key)
    if ignored:
        print("[aviso] Há sessões não verificadas; elas foram preservadas e não serão carregadas.")
    if sessions:
        while True:
            choice = input("Continuar última sessão verificada? [S/n] ").strip().lower()
            if choice in ("", "s", "sim"):
                return sessions[0][1]
            if choice in ("n", "nao", "não"):
                break
            print("Digite S para continuar ou N para iniciar outra sessão.")
    return new_session_id()


def build_agent(session_id, storage_dir, api_key, *, signing_key=None):
    configure_logging()
    manager = SecureSessionManager(session_id, storage_dir, signing_key=signing_key)
    try:
        return Agent(
            model=OpenAIModel(
                client_args={"api_key": api_key, "timeout": 15, "max_retries": 0},
                model_id=os.getenv("OPENAI_MODEL_ID") or "gpt-4o-mini",
                params={"max_completion_tokens": MAX_OUTPUT_TOKENS},
            ),
            tools=[current_datetime, weather_forecast],
            system_prompt=(os.getenv("SYSTEM_PROMPT") or DEFAULT_PROMPT) + "\n" + SAFETY_PROMPT,
            session_manager=manager,
            hooks=[TurnBudget()],
            retry_strategy=None,
            conversation_manager=SlidingWindowConversationManager(window_size=20),
            callback_handler=None,
        )
    except Exception:
        manager.close()
        raise


def close_agent(agent):
    manager = getattr(agent, "_session_manager", None)
    if manager is not None:
        manager.close()


async def stream_reply(agent, text):
    """Saída com prazo global, limite de tamanho e filtro de terminal."""
    if len(text) > MAX_INPUT_CHARS:
        raise BudgetExceeded()
    clean = TerminalFilter()
    length = 0
    stream = agent.stream_async(text)
    try:
        async with asyncio.timeout(TURN_TIMEOUT):
            async for event in stream:
                if isinstance(event.get("data"), str):
                    length += len(event["data"])
                    if length > MAX_OUTPUT_CHARS:
                        raise BudgetExceeded()
                    yield clean.feed(event["data"])
    finally:
        await stream.aclose()


async def chat(agent):
    while True:
        user_input = input("\nVocê: ").strip()
        if not user_input:
            continue
        if user_input.lower() in EXIT_COMMANDS:
            return
        if len(user_input) > MAX_INPUT_CHARS:
            print(f"[aviso] Use até {MAX_INPUT_CHARS} caracteres por mensagem.")
            continue
        print("Agente: ", end="", flush=True)
        try:
            async for text in stream_reply(agent, user_input):
                print(text, end="", flush=True)
        except IntegrityError:
            print("\n[erro] A integridade da sessão falhou. Encerre e inicie uma nova sessão.")
            return
        except Exception as error:
            print("\n[erro] " + public_error(error))
        print()


def main():
    for output in (sys.stdout, sys.stderr):
        if hasattr(output, "reconfigure"):
            output.reconfigure(encoding="utf-8")
    configure_logging()
    load_dotenv(ROOT / ".env")
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        print("[erro] OPENAI_API_KEY não definida. Configure-a no arquivo .env.")
        return 1
    agent = None
    try:
        configured = Path(os.getenv("SESSION_STORAGE_DIR") or "./sessions")
        storage = (configured if configured.is_absolute() else ROOT / configured) / "verified-v1"
        private_directory(storage)
        key = load_signing_key()
        print("=== Chat IA Café === (digite 'sair' para encerrar)")
        session_id = choose_session_id(storage, key)
        try:
            agent = build_agent(session_id, storage, api_key, signing_key=key)
        except Exception:
            print("[aviso] Sessão indisponível. Tentando uma nova sessão verificada.")
            session_id = new_session_id()
            agent = build_agent(session_id, storage, api_key, signing_key=key)
        print(f"Sessão: {session_id}")
        asyncio.run(chat(agent))
        return 0
    except (KeyboardInterrupt, EOFError):
        return 0
    except Exception:
        print("[erro] Não foi possível abrir o chat. Verifique configuração e permissões locais.")
        return 1
    finally:
        if agent is not None:
            close_agent(agent)


if __name__ == "__main__":
    status = main()
    print("\nAté logo!")
    sys.exit(status)
