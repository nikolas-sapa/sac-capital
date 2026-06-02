"""One-way Telegram alert sink using aiogram 3.x."""
from __future__ import annotations

from typing import Any

from aiogram import Bot

from core.execution.base import Fill


class TelegramAlerts:
    def __init__(self, token: str, chat_id: str) -> None:
        self._token = token
        self._chat_id = chat_id

    # ------------------------------------------------------------------
    # Polymarket formatters
    # ------------------------------------------------------------------

    def format_fill(self, fill: Fill) -> str:
        """Return a plain-text message describing a paper fill."""
        label = fill.signal.market.outcome_by_token(fill.signal.token_id).label
        edge_pct = (fill.signal.fair_prob - fill.avg_price) / fill.avg_price * 100
        edge_icon = "🟢" if edge_pct > 0 else "🔴"
        return (
            f"✅ PAPER FILL\n"
            f"{fill.signal.market.question}\n"
            f"Outcome: {label} ({fill.signal.token_id})\n"
            f"Stake: {fill.stake:.2f}  Shares: {fill.shares:.4f}  AvgPrice: {fill.avg_price:.4f}\n"
            f"FairProb: {fill.signal.fair_prob:.3f}  {edge_icon} Edge: {edge_pct:+.1f}%  Mode: {fill.mode}"
        )

    def format_polymarket_scan(
        self,
        markets_count: int,
        strategy_names: list[str],
    ) -> str:
        strats = " · ".join(strategy_names)
        return (
            f"⚡ POLYMARKET SCAN — {markets_count} markets\n"
            f"Strategies: {strats}"
        )

    def format_error(self, message: str) -> str:
        return f"🚨 ERROR\n{message}"

    # ------------------------------------------------------------------
    # Equity formatters
    # ------------------------------------------------------------------

    def format_equity_scan(
        self,
        swing_candidates: list[Any],
        core_candidates: list[Any],
        analyst_count: int,
    ) -> str:
        _EVENT_ICON = {
            "earnings_approaching":    "📅",
            "earnings_surprise_drift": "📈",
            "material_filing":         "📋",
        }
        lines = [
            f"📊 EQUITY SCAN — {len(swing_candidates)} swing · {len(core_candidates)} core",
            f"Sending {analyst_count} to analyst",
        ]
        if swing_candidates:
            lines.append("")
            lines.append("⚡ Swing pipeline:")
            for c in swing_candidates:
                icon = _EVENT_ICON.get(c.event_type.value, "🔹")
                days = f" · in {c.days_to_event}d" if c.days_to_event is not None else ""
                lines.append(f"  {icon} {c.instrument.ticker}{days} — {c.evidence[:65]}")
        if core_candidates:
            lines.append("")
            lines.append("✅ Core screen passed:")
            for c in core_candidates:
                lines.append(f"  🔷 {c.instrument.ticker} ({c.score:.2f}) — {c.evidence[:65]}")
        return "\n".join(lines)

    def format_equity_open(self, rec: Any, fill: Any) -> str:
        risk_pct = abs(rec.entry - rec.stop_loss) / rec.entry * 100
        reward_pct = abs(rec.take_profit - rec.entry) / rec.entry * 100
        rr = reward_pct / risk_pct if risk_pct > 0 else 0.0
        thesis = rec.thesis[:160] + "..." if len(rec.thesis) > 160 else rec.thesis
        return (
            f"🟢 PAPER OPEN — {rec.instrument.ticker} · {rec.instrument.name}\n"
            f"Entry ${rec.entry:.2f}  🛑 Stop ${rec.stop_loss:.2f}  🎯 Target ${rec.take_profit:.2f}\n"
            f"Risk {risk_pct:.1f}%  Reward {reward_pct:.1f}%  R/R {rr:.1f}x\n"
            f"Shares {fill.shares:.4f}  Confidence {rec.confidence:.0%}\n"
            f"📍 {rec.catalyst}\n"
            f"💡 {thesis}"
        )

    def format_equity_exit(
        self,
        exit_signal: Any,
        ticker: str,
        entry_price: float,
        shares: float,
        portfolio_stats: dict[str, Any],
    ) -> str:
        pnl = (exit_signal.exit_price - entry_price) * shares
        pnl_pct = (exit_signal.exit_price - entry_price) / entry_price * 100
        is_win = pnl > 0
        reason_map = {
            "stop_hit":   ("🛑", "STOP HIT",   "LOSS"),
            "target_hit": ("🎯", "TARGET HIT",  "WIN"),
            "time_stop":  ("⏱", "TIME STOP",  "WIN" if is_win else "LOSS"),
        }
        icon, reason_label, result_label = reason_map.get(
            exit_signal.reason, ("⚪", exit_signal.reason.upper(), "WIN" if is_win else "LOSS")
        )
        result_icon = "✅" if is_win else "❌"
        s = portfolio_stats
        win_rate = s["win_rate"] * 100
        pnl_sign = "+" if pnl >= 0 else ""
        lines = [
            f"{icon} {reason_label} — {ticker}   {result_icon} {result_label}",
            f"${entry_price:.2f} → ${exit_signal.exit_price:.2f}",
            f"P&L  {pnl_sign}${pnl:.2f}  ({pnl_sign}{pnl_pct:.1f}%)",
            f"──────────────────",
            f"📊 {s['closed_count']} closed  {s['wins']}W {s['losses']}L  Win {win_rate:.0f}%"
            f"  Realized {'+' if s['realized_pnl'] >= 0 else ''}${s['realized_pnl']:.2f}",
        ]
        if s["open_count"] > 0:
            unrl = s["unrealized_pnl"]
            lines.append(
                f"📌 {s['open_count']} open  Unrealized {'+' if unrl >= 0 else ''}${unrl:.2f}"
            )
        return "\n".join(lines)

    def format_equity_portfolio(self, stats: dict[str, Any]) -> str:
        s = stats
        total_pnl = s["realized_pnl"] + s["unrealized_pnl"]
        win_rate = s["win_rate"] * 100
        realized = s["realized_pnl"]
        lines = [
            f"💼 PORTFOLIO — Equity paper",
            f"{'─' * 22}",
            f"📌 Open:    {s['open_count']} position(s)",
            f"📋 Closed:  {s['closed_count']} trade(s)  {s['wins']}W {s['losses']}L  Win {win_rate:.0f}%",
            f"💰 Realized:    {'+' if realized >= 0 else ''}${realized:.2f}",
        ]
        if s["open_count"] > 0:
            unrl = s["unrealized_pnl"]
            lines.append(f"📈 Unrealized:  {'+' if unrl >= 0 else ''}${unrl:.2f}")
            lines.append(f"🏁 Total:       {'+' if total_pnl >= 0 else ''}${total_pnl:.2f}")
            lines.append("")
            lines.append("Open positions:")
            for pos in s.get("open_positions", []):
                unrl_pos = pos.get("unrealized_pnl") or 0.0
                mark = pos.get("mark_price") or pos.get("entry_price", 0.0)
                arrow = "↑" if unrl_pos >= 0 else "↓"
                lines.append(
                    f"  {arrow} {pos['ticker']}  mark ${mark:.2f}"
                    f"  {'+' if unrl_pos >= 0 else ''}${unrl_pos:.2f}"
                )
        return "\n".join(lines)

    # ------------------------------------------------------------------

    async def send(self, text: str) -> None:
        """Send text via aiogram Bot; session closes on exit of async context."""
        async with Bot(self._token) as bot:
            await bot.send_message(self._chat_id, text)
