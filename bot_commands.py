"""Telegram command bot — long-poll loop.

Run as a persistent process via launchd KeepAlive.
- Waits up to 25s for a message (Telegram long-poll)
- Processes any /commands and replies
- Exits; launchd immediately restarts for the next cycle
- Response latency: < 1 second after user sends a command

Only responds to TELEGRAM_CHAT_ID (security gate).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

from core.bot.command_handler import CommandHandler
from core.config import load_config

_OFFSET_FILE = Path("data/bot_offset.txt")
_TG_BASE = "https://api.telegram.org/bot"


def _get_updates(token: str, offset: int) -> list[dict]:
    try:
        r = httpx.get(
            f"{_TG_BASE}{token}/getUpdates",
            params={"offset": offset, "timeout": 25, "limit": 20},
            timeout=35,  # slightly longer than Telegram's timeout
        )
        r.raise_for_status()
        return r.json().get("result", [])
    except httpx.TimeoutException:
        return []
    except Exception as exc:
        safe_msg = str(exc).replace(token, "<token>")
        print(f"getUpdates error: {safe_msg}", flush=True)
        time.sleep(30)
        return []


def _send(token: str, chat_id: str, text: str) -> None:
    try:
        httpx.post(
            f"{_TG_BASE}{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception as exc:
        safe_msg = str(exc).replace(token, "<token>")
        print(f"sendMessage error: {safe_msg}", flush=True)


def _register_commands(token: str) -> None:
    """Register bot command menu shown when user types '/' in Telegram."""
    commands = [
        {"command": "help",      "description": "List all commands"},
        {"command": "stats",     "description": "Equity portfolio summary"},
        {"command": "positions", "description": "Open equity positions with PnL"},
        {"command": "alpaca",    "description": "Alpaca paper config status"},
        {"command": "orders",    "description": "Broker order status from local ledger"},
        {"command": "risk",      "description": "Risk limits and local exposure"},
        {"command": "markets",   "description": "Open Polymarket positions"},
        {"command": "pnl",       "description": "Combined P&L report"},
        {"command": "kill",      "description": "Kill gate progress to live trading"},
    ]
    try:
        httpx.post(
            f"{_TG_BASE}{token}/setMyCommands",
            json={"commands": commands},
            timeout=10,
        )
    except Exception:
        pass


def main() -> None:
    settings = load_config()
    if not settings.telegram_bot_token:
        print("No TELEGRAM_BOT_TOKEN — exiting.", flush=True)
        sys.exit(0)

    token = settings.telegram_bot_token
    allowed_chat = settings.telegram_chat_id

    # Register command menu once per process start (cheap, idempotent)
    _register_commands(token)

    offset = int(_OFFSET_FILE.read_text().strip()) if _OFFSET_FILE.exists() else 0
    handler = CommandHandler()

    updates = _get_updates(token, offset)

    for update in updates:
        offset = update["update_id"] + 1
        msg = update.get("message") or update.get("channel_post") or {}
        if not msg:
            continue

        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = (msg.get("text") or "").strip()

        if chat_id != allowed_chat:
            continue
        if not text.startswith("/"):
            continue

        print(f"cmd: {text!r} from {chat_id}", flush=True)
        response = handler.dispatch(text)
        _send(token, chat_id, response)

    _OFFSET_FILE.parent.mkdir(exist_ok=True)
    _OFFSET_FILE.write_text(str(offset))


if __name__ == "__main__":
    main()
