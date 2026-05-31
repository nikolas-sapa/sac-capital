"""One-way Telegram alert sink using aiogram 3.x."""
from __future__ import annotations

from aiogram import Bot

from core.execution.base import Fill


class TelegramAlerts:
    def __init__(self, token: str, chat_id: str) -> None:
        self._token = token
        self._chat_id = chat_id

    def format_fill(self, fill: Fill) -> str:
        """Return a plain-text message describing a paper fill."""
        label = fill.signal.market.outcome_by_token(fill.signal.token_id).label
        return (
            f"[PAPER FILL] {fill.signal.market.question}\n"
            f"Outcome: {label} ({fill.signal.token_id})\n"
            f"Stake: {fill.stake:.2f}  Shares: {fill.shares:.4f}  AvgPrice: {fill.avg_price:.4f}\n"
            f"FairProb: {fill.signal.fair_prob:.3f}  Mode: {fill.mode}"
        )

    def format_error(self, message: str) -> str:
        """Return a plain-text error message."""
        return f"[ERROR] {message}"

    async def send(self, text: str) -> None:
        """Send text via aiogram Bot; session closes on exit of async context."""
        async with Bot(self._token) as bot:
            await bot.send_message(self._chat_id, text)
