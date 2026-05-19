from __future__ import annotations

import argparse
import sys

from .config import AgentConfig, load_config
from .llm import OllamaClient, OllamaError
from .prompts import SYSTEM_PROMPT
from .tools.files import project_tree, read_file
from .tools.search import search_code
from .tools.shell import run_command


HELP_TEXT = """Commands:
  /help                  Show this help
  /model                 Show active model and Ollama URL
  /read <path>           Load a file into context
  /search <query>        Search workspace and load results into context
  /tree                  Load compact project tree into context
  /run <command>         Run a local command and load output into context
  /clear                 Clear conversation context
  /exit                  Quit
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Free local AI coding agent")
    parser.add_argument(
        "--message",
        "-m",
        help="Send one message and exit instead of starting the interactive shell.",
    )
    return parser


def new_messages() -> list[dict[str, str]]:
    return [{"role": "system", "content": SYSTEM_PROMPT}]


def add_context(messages: list[dict[str, str]], title: str, content: str) -> None:
    messages.append(
        {
            "role": "user",
            "content": f"{title}\n\n```text\n{content}\n```",
        }
    )


def print_agent(text: str) -> None:
    print("\nAgent:")
    print(text)


def handle_command(config: AgentConfig, messages: list[dict[str, str]], raw: str) -> bool:
    command, _, value = raw.partition(" ")
    value = value.strip()

    if command in {"/exit", "/quit"}:
        raise KeyboardInterrupt

    if command == "/help":
        print(HELP_TEXT)
        return True

    if command == "/model":
        print(f"Model: {config.model}")
        print(f"Ollama: {config.ollama_url}")
        print(f"Workspace: {config.workspace}")
        return True

    if command == "/clear":
        messages.clear()
        messages.extend(new_messages())
        print("Conversation context cleared.")
        return True

    if command == "/read":
        if not value:
            print("Usage: /read <path>")
            return True
        content = read_file(config, value)
        add_context(messages, f"File `{value}`:", content)
        print(f"Loaded file into context: {value}")
        return True

    if command == "/search":
        if not value:
            print("Usage: /search <query>")
            return True
        content = search_code(config, value)
        add_context(messages, f"Search results for `{value}`:", content)
        print(f"Loaded search results into context for: {value}")
        return True

    if command == "/tree":
        content = project_tree(config)
        add_context(messages, "Project tree:", content)
        print("Loaded project tree into context.")
        return True

    if command == "/run":
        if not value:
            print("Usage: /run <command>")
            return True
        content = run_command(config, value)
        add_context(messages, f"Command output for `{value}`:", content)
        print(content)
        print("Loaded command output into context.")
        return True

    return False


def ask_once(client: OllamaClient, messages: list[dict[str, str]], user_message: str) -> str:
    messages.append({"role": "user", "content": user_message})
    answer = client.chat(messages)
    messages.append({"role": "assistant", "content": answer})
    return answer


def interactive(config: AgentConfig) -> int:
    client = OllamaClient(config)
    messages = new_messages()

    print("Local AI Coding Agent")
    print(f"Model: {config.model}")
    print(f"Workspace: {config.workspace}")
    print("Type /help for commands, /exit to quit.")

    while True:
        try:
            raw = input("\nYou: ").strip()
            if not raw:
                continue

            if raw.startswith("/") and handle_command(config, messages, raw):
                continue

            answer = ask_once(client, messages, raw)
            print_agent(answer)
        except KeyboardInterrupt:
            print("\nGoodbye.")
            return 0
        except OllamaError as exc:
            print(f"\nOllama error: {exc}", file=sys.stderr)
        except Exception as exc:
            print(f"\nError: {exc}", file=sys.stderr)


def main() -> int:
    args = build_parser().parse_args()
    config = load_config()
    client = OllamaClient(config)
    messages = new_messages()

    if args.message:
        try:
            print(ask_once(client, messages, args.message))
            return 0
        except OllamaError as exc:
            print(f"Ollama error: {exc}", file=sys.stderr)
            return 1

    return interactive(config)
