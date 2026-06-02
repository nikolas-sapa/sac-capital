"""Telegram bot command handler — reads from equity + polymarket ledgers."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class CommandHandler:
    """Route /commands to formatted responses.

    Reads directly from sqlite — no ORM layer needed for read-only queries.
    """

    COMMANDS = {
        "/help":      "List all commands",
        "/stats":     "Equity portfolio summary",
        "/positions": "Open equity positions with entry/mark/PnL",
        "/markets":   "Open Polymarket positions",
        "/pnl":       "Combined P&L across equity + Polymarket",
        "/kill":      "Kill gate progress toward live trading",
    }

    def __init__(
        self,
        equity_db: str | Path = "data/equity.db",
        polymarket_db: str | Path = "data/ledger.db",
        forward_paper_db: str | Path = "data/forward_paper.db",
    ) -> None:
        self._eq_path = Path(equity_db)
        self._pm_path = Path(polymarket_db)
        self._fp_path = Path(forward_paper_db)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def dispatch(self, text: str) -> str:
        parts = text.strip().lower().split()
        cmd = parts[0] if parts else ""
        dispatch_map = {
            "/help":      self._cmd_help,
            "/stats":     self._cmd_stats,
            "/positions": self._cmd_positions,
            "/pos":       self._cmd_positions,
            "/markets":   self._cmd_markets,
            "/pnl":       self._cmd_pnl,
            "/kill":      self._cmd_kill,
        }
        fn = dispatch_map.get(cmd)
        if fn is None:
            return f"❓ Unknown command: {cmd}\nType /help for the list."
        try:
            return fn()
        except Exception as exc:
            return f"🚨 Error running {cmd}: {exc}"

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def _cmd_help(self) -> str:
        lines = ["🤖 Polymarket Bot Commands", "─" * 26]
        for cmd, desc in self.COMMANDS.items():
            lines.append(f"{cmd:<12}  {desc}")
        return "\n".join(lines)

    def _cmd_stats(self) -> str:
        if not self._eq_path.exists():
            return "📊 No equity data yet."
        con = sqlite3.connect(str(self._eq_path))
        con.row_factory = sqlite3.Row
        closed = con.execute("SELECT realized_pnl FROM positions WHERE status='closed'").fetchall()
        open_rows = con.execute(
            "SELECT ticker, entry_price, mark_price, unrealized_pnl, stop_loss, take_profit "
            "FROM positions WHERE status='open'"
        ).fetchall()
        con.close()

        total = len(closed)
        wins = sum(1 for r in closed if r["realized_pnl"] > 0)
        losses = total - wins
        win_rate = wins / total * 100 if total > 0 else 0.0
        realized = sum(r["realized_pnl"] for r in closed)
        unrealized = sum(r["unrealized_pnl"] or 0.0 for r in open_rows)
        total_pnl = realized + unrealized

        lines = [
            "📊 EQUITY PORTFOLIO",
            "─" * 22,
            f"📌 Open:    {len(open_rows)} position(s)",
            f"📋 Closed:  {total} trade(s)  {wins}W {losses}L  Win {win_rate:.0f}%",
            f"💰 Realized:    {_fmt_pnl(realized)}",
        ]
        if open_rows:
            lines.append(f"📈 Unrealized:  {_fmt_pnl(unrealized)}")
            lines.append(f"🏁 Total:       {_fmt_pnl(total_pnl)}")
        return "\n".join(lines)

    def _cmd_positions(self) -> str:
        if not self._eq_path.exists():
            return "📌 No open equity positions."
        con = sqlite3.connect(str(self._eq_path))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT ticker, entry_price, mark_price, stop_loss, take_profit, "
            "unrealized_pnl, opened_at, strategy "
            "FROM positions WHERE status='open' ORDER BY opened_at"
        ).fetchall()
        con.close()

        if not rows:
            return "📌 No open equity positions."

        lines = [f"📌 OPEN POSITIONS ({len(rows)})", "─" * 26]
        for r in rows:
            mark = r["mark_price"] or r["entry_price"]
            unrl = r["unrealized_pnl"] or 0.0
            pct = (mark - r["entry_price"]) / r["entry_price"] * 100
            arrow = "↑" if unrl >= 0 else "↓"
            opened = r["opened_at"][:10] if r["opened_at"] else "?"
            lines += [
                f"",
                f"{arrow} {r['ticker']}",
                f"  Entry ${r['entry_price']:.2f}  ·  Mark ${mark:.2f}",
                f"  Unrl  {_fmt_pnl(unrl)}  ({pct:+.1f}%)",
                f"  🛑 ${r['stop_loss']:.2f}    🎯 ${r['take_profit']:.2f}",
                f"  Opened {opened}",
            ]
        return "\n".join(lines)

    def _cmd_markets(self) -> str:
        if not self._pm_path.exists():
            return "⚡ No Polymarket positions yet."
        con = sqlite3.connect(str(self._pm_path))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT question, stake, avg_price, fair_prob, strategy, timestamp "
            "FROM fills WHERE resolved=0 ORDER BY timestamp DESC LIMIT 10"
        ).fetchall()
        con.close()

        if not rows:
            return "⚡ No open Polymarket positions."

        lines = [f"⚡ POLYMARKET POSITIONS ({len(rows)})", "─" * 28]
        for r in rows:
            edge = (r["fair_prob"] - r["avg_price"]) / r["avg_price"] * 100
            edge_icon = "🟢" if edge > 0 else "🔴"
            q = r["question"][:55] + "…" if len(r["question"]) > 55 else r["question"]
            ts = r["timestamp"][:10] if r["timestamp"] else "?"
            lines += [
                "",
                f"• {q}",
                f"  Stake ${r['stake']:.2f}  ·  Price {r['avg_price']:.4f}",
                f"  Fair {r['fair_prob']:.3f}  {edge_icon} Edge {edge:+.1f}%  [{r['strategy']}]",
                f"  {ts}",
            ]
        return "\n".join(lines)

    def _cmd_pnl(self) -> str:
        lines = ["💰 P&L SUMMARY", "─" * 22]

        # Equity
        eq_realized = eq_unrealized = 0.0
        eq_open = 0
        if self._eq_path.exists():
            con = sqlite3.connect(str(self._eq_path))
            con.row_factory = sqlite3.Row
            closed = con.execute("SELECT realized_pnl FROM positions WHERE status='closed'").fetchall()
            open_rows = con.execute("SELECT unrealized_pnl FROM positions WHERE status='open'").fetchall()
            con.close()
            eq_realized = sum(r["realized_pnl"] for r in closed)
            eq_unrealized = sum(r["unrealized_pnl"] or 0.0 for r in open_rows)
            eq_open = len(open_rows)

        # Polymarket
        pm_realized = 0.0
        pm_open = 0
        if self._pm_path.exists():
            con = sqlite3.connect(str(self._pm_path))
            con.row_factory = sqlite3.Row
            pm_rows = con.execute("SELECT pnl FROM fills WHERE resolved=1").fetchall()
            pm_open = con.execute("SELECT COUNT(*) FROM fills WHERE resolved=0").fetchone()[0]
            con.close()
            pm_realized = sum(r["pnl"] for r in pm_rows if r["pnl"] is not None)

        total_realized = eq_realized + pm_realized
        total_unrealized = eq_unrealized

        lines += [
            "",
            "📈 Equity:",
            f"  Realized   {_fmt_pnl(eq_realized)}",
            f"  Unrealized {_fmt_pnl(eq_unrealized)}  ({eq_open} open)",
            "",
            "⚡ Polymarket:",
            f"  Realized   {_fmt_pnl(pm_realized)}",
            f"  Open       {pm_open} position(s)",
            "",
            "─" * 22,
            f"🏁 Combined realized:  {_fmt_pnl(total_realized)}",
        ]
        if eq_unrealized:
            lines.append(f"📌 Unrealized:         {_fmt_pnl(total_unrealized)}")
        return "\n".join(lines)

    def _cmd_kill(self) -> str:
        if not self._fp_path.exists():
            return "🎯 Kill gate: 0 / 100 paper trades recorded yet."
        con = sqlite3.connect(str(self._fp_path))
        count = con.execute("SELECT COUNT(*) FROM forward_paper").fetchone()[0]
        con.close()

        pct = min(count / 100 * 100, 100)
        bar_filled = int(pct / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        ready = "🟢 READY — review before going live" if count >= 100 else "🔴 NOT ready"
        return (
            f"🎯 KILL GATE\n"
            f"─────────────────────\n"
            f"Progress: {count} / 100 paper trades\n"
            f"[{bar}] {pct:.0f}%\n"
            f"Status: {ready}"
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _fmt_pnl(val: float) -> str:
    sign = "+" if val >= 0 else ""
    return f"{sign}${val:.2f}"
