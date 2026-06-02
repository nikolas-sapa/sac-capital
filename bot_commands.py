"""Telegram command poller — run every 2 minutes via launchd.

Checks for new messages, routes /commands, replies, advances offset.
Only responds to the configured TELEGRAM_CHAT_ID (security gate).
"""
from __future__ import annotations

import sys
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
            params={"offset": offset, "timeout": 5, "limit": 20},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("result", [])
    except Exception:
        return []


def _send(token: str, chat_id: str, text: str) -> None:
    try:
        httpx.post(
            f"{_TG_BASE}{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception:
        pass


def main() -> None:
    settings = load_config()
    if not settings.telegram_bot_token:
        print("No TELEGRAM_BOT_TOKEN configured — exiting.")
        sys.exit(0)

    offset = int(_OFFSET_FILE.read_text().strip()) if _OFFSET_FILE.exists() else 0
    handler = CommandHandler()
    token = settings.telegram_bot_token
    allowed_chat = settings.telegram_chat_id

    updates = _get_updates(token, offset)
    for update in updates:
        offset = update["update_id"] + 1
        msg = update.get("message") or update.get("channel_post", {})
        if not msg:
            continue

        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = (msg.get("text") or "").strip()

        # Security: ignore messages not from the configured chat
        if chat_id != allowed_chat:
            continue
        if not text.startswith("/"):
            continue

        response = handler.dispatch(text)
        _send(token, chat_id, response)

    _OFFSET_FILE.parent.mkdir(exist_ok=True)
    _OFFSET_FILE.write_text(str(offset))


if __name__ == "__main__":
    main()
