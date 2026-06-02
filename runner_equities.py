"""Equities runner — screen → analyse → risk-gate → paper-open → nightly mark.

Usage:
    uv run python runner_equities.py                    # single pass
    uv run python runner_equities.py --no-analyse       # screen only (no Claude API)
    uv run python runner_equities.py --mark-only        # mark-to-market + exit check

Requires ANTHROPIC_API_KEY in .env for the analyse phase.
All trades are paper-only; LIVE mode does not exist yet.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from core.alerts.telegram import TelegramAlerts
from core.assets.instrument import CapTier, Instrument
from core.config import load_config
from core.claude_client import ClaudeCodeClient
from equities.analysis.analyst import EquityAnalyst
from equities.analysis.budget import DailyBudget
from equities.data.calendar import YFinanceCalendar
from equities.data.filings import SECEdgarFilings
from equities.data.fundamentals import YFinanceFundamentals
from equities.data.prices import YFinancePriceFeed
from equities.killgate.tracker import ForwardPaperTracker
from equities.ledger_equity import EquityLedger
from equities.paper import EquityPaperTracker
from equities.risk.kernel import RiskKernel
from equities.screen.event_screen import (
    CalendarAdapter,
    EventScreen,
    FilingsAdapter,
)
from equities.screen.quality_screen import QualityScreen

# ---------------------------------------------------------------------------
# Default universe (extend via --universe flag or editing this list)
# ---------------------------------------------------------------------------

DEFAULT_SWING_UNIVERSE: list[Instrument] = [
    # Original mid-cap catalyst plays
    Instrument("ARWR",  "Arrowhead Pharmaceuticals", "NASDAQ", CapTier.MID),
    Instrument("PRCT",  "PROCEPT BioRobotics",       "NASDAQ", CapTier.MID),
    Instrument("PGNY",  "Progyny",                    "NASDAQ", CapTier.MID),
    Instrument("SMCI",  "Super Micro Computer",       "NASDAQ", CapTier.MID),
    Instrument("FIGS",  "FIGS",                       "NYSE",   CapTier.MID),
    Instrument("XPEL",  "XPEL",                       "NASDAQ", CapTier.SMALL),
    Instrument("KLIC",  "Kulicke and Soffa",          "NASDAQ", CapTier.MID),
    # High-growth / trendy — analyst fires on earnings/filings catalysts
    Instrument("PLTR",  "Palantir",                   "NASDAQ", CapTier.MID),
    Instrument("HOOD",  "Robinhood",                  "NASDAQ", CapTier.MID),
    Instrument("COIN",  "Coinbase",                   "NASDAQ", CapTier.MID),
    Instrument("RKLB",  "Rocket Lab",                 "NASDAQ", CapTier.SMALL),
    Instrument("SOFI",  "SoFi Technologies",          "NASDAQ", CapTier.MID),
    Instrument("APP",   "AppLovin",                   "NASDAQ", CapTier.MID),
    Instrument("AXON",  "Axon Enterprise",            "NASDAQ", CapTier.MID),
    Instrument("CRWD",  "CrowdStrike",                "NASDAQ", CapTier.LARGE),
    Instrument("NET",   "Cloudflare",                 "NYSE",   CapTier.MID),
    Instrument("DDOG",  "Datadog",                    "NASDAQ", CapTier.MID),
    Instrument("SNOW",  "Snowflake",                  "NYSE",   CapTier.MID),
    Instrument("IONQ",  "IonQ",                       "NYSE",   CapTier.SMALL),
    Instrument("MSTR",  "MicroStrategy",              "NASDAQ", CapTier.MID),
    Instrument("SQ",    "Block",                      "NYSE",   CapTier.MID),
    Instrument("AFRM",  "Affirm",                     "NASDAQ", CapTier.MID),
    Instrument("NU",    "Nu Holdings",                "NYSE",   CapTier.MID),
    Instrument("TSLA",  "Tesla",                      "NASDAQ", CapTier.LARGE),
    Instrument("ARM",   "Arm Holdings",               "NASDAQ", CapTier.LARGE),
    Instrument("CVNA",  "Carvana",                    "NYSE",   CapTier.MID),
    Instrument("RBRK",  "Rubrik",                     "NYSE",   CapTier.MID),
    Instrument("SOUN",  "SoundHound AI",              "NASDAQ", CapTier.SMALL),
    # AI chips & semiconductor infrastructure
    Instrument("AMD",   "Advanced Micro Devices",     "NASDAQ", CapTier.LARGE),
    Instrument("MU",    "Micron Technology",          "NASDAQ", CapTier.LARGE),
    Instrument("MRVL",  "Marvell Technology",         "NASDAQ", CapTier.MID),
    Instrument("ALAB",  "Astera Labs",                "NASDAQ", CapTier.SMALL),
    Instrument("NBIS",  "Nebius Group",               "NASDAQ", CapTier.SMALL),
    Instrument("QCOM",  "Qualcomm",                   "NASDAQ", CapTier.LARGE),
    Instrument("ONTO",  "Onto Innovation",            "NYSE",   CapTier.MID),
    # Cybersecurity
    Instrument("ZS",    "Zscaler",                    "NASDAQ", CapTier.MID),
    Instrument("S",     "SentinelOne",                "NYSE",   CapTier.MID),
    Instrument("PANW",  "Palo Alto Networks",         "NASDAQ", CapTier.LARGE),
    Instrument("OKTA",  "Okta",                       "NASDAQ", CapTier.MID),
    Instrument("FTNT",  "Fortinet",                   "NASDAQ", CapTier.LARGE),
    # Cloud / AI SaaS
    Instrument("NOW",   "ServiceNow",                 "NYSE",   CapTier.LARGE),
    Instrument("CRM",   "Salesforce",                 "NYSE",   CapTier.LARGE),
    Instrument("MNDY",  "Monday.com",                 "NASDAQ", CapTier.MID),
    Instrument("GTLB",  "GitLab",                     "NASDAQ", CapTier.MID),
    Instrument("HUBS",  "HubSpot",                    "NYSE",   CapTier.MID),
    Instrument("BILL",  "Bill.com",                   "NYSE",   CapTier.MID),
    # E-commerce / consumer tech
    Instrument("SHOP",  "Shopify",                    "NYSE",   CapTier.LARGE),
    Instrument("MELI",  "MercadoLibre",               "NASDAQ", CapTier.LARGE),
    Instrument("TOST",  "Toast",                      "NYSE",   CapTier.MID),
    Instrument("GLBE",  "Global-E Online",            "NASDAQ", CapTier.SMALL),
    Instrument("UBER",  "Uber",                       "NYSE",   CapTier.LARGE),
    # Emerging / speculative tech
    Instrument("RBLX",  "Roblox",                     "NYSE",   CapTier.MID),
    Instrument("RXRX",  "Recursion Pharmaceuticals",  "NASDAQ", CapTier.SMALL),
    Instrument("HIMS",  "Hims & Hers",                "NYSE",   CapTier.SMALL),
    Instrument("AI",    "C3.ai",                      "NYSE",   CapTier.SMALL),
    Instrument("BBAI",  "BigBear.ai",                 "NYSE",   CapTier.SMALL),
]

DEFAULT_CORE_UNIVERSE: list[Instrument] = [
    # Quality large-caps — scored on fundamentals (margins, PE, growth)
    Instrument("MSFT",  "Microsoft",       "NASDAQ", CapTier.LARGE),
    Instrument("AAPL",  "Apple",           "NASDAQ", CapTier.LARGE),
    Instrument("GOOGL", "Alphabet",        "NASDAQ", CapTier.LARGE),
    Instrument("META",  "Meta Platforms",  "NASDAQ", CapTier.LARGE),
    Instrument("NVDA",  "NVIDIA",          "NASDAQ", CapTier.LARGE),
    Instrument("AMZN",  "Amazon",          "NASDAQ", CapTier.LARGE),
    Instrument("V",     "Visa",            "NYSE",   CapTier.LARGE),
    Instrument("MA",    "Mastercard",      "NYSE",   CapTier.LARGE),
    Instrument("JPM",   "JPMorgan Chase",  "NYSE",   CapTier.LARGE),
    Instrument("UNH",   "UnitedHealth",    "NYSE",   CapTier.LARGE),
    Instrument("LLY",   "Eli Lilly",       "NYSE",   CapTier.LARGE),
    Instrument("TSM",   "TSMC",            "NYSE",   CapTier.LARGE),
    Instrument("AVGO",  "Broadcom",        "NASDAQ", CapTier.LARGE),
    Instrument("ASML",  "ASML Holding",    "NASDAQ", CapTier.LARGE),
    Instrument("ORCL",  "Oracle",          "NYSE",   CapTier.LARGE),
]


# ---------------------------------------------------------------------------
# Price provider adapter (satisfies analyst.PriceProvider protocol)
# ---------------------------------------------------------------------------

class _PriceAdapter:
    def __init__(self, feed: YFinancePriceFeed) -> None:
        self._feed = feed

    def latest_close(self, ticker: str) -> float | None:
        try:
            series = self._feed.history(ticker, period="5d")
            bar = series.latest
            return bar.close if bar is not None else None
        except Exception:
            return None


class _NewsAdapter:
    def headlines(self, ticker: str, limit: int = 8) -> list[str]:
        try:
            import yfinance as yf
            news = yf.Ticker(ticker).news or []
            return [n.get("content", {}).get("title") or n.get("title", "") for n in news[:limit]]
        except Exception:
            return []


class _FilingsSummaryAdapter:
    def __init__(self, client: SECEdgarFilings) -> None:
        self._client = client

    def summary(self, ticker: str, days: int = 90) -> list[str]:
        filings = self._client.recent(ticker, days=days)
        return [
            f"{f.form_type} ({f.filed_date}) — items: {', '.join(f.items)}"
            for f in filings
        ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_once(
    swing_universe: list[Instrument],
    core_universe: list[Instrument],
    no_analyse: bool = False,
    mark_only: bool = False,
) -> None:
    settings = load_config()

    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    equity_ledger = EquityLedger(data_dir / "equity.db")
    fp_tracker = ForwardPaperTracker(data_dir / "forward_paper.db")

    price_feed = YFinancePriceFeed()
    prices = _PriceAdapter(price_feed)
    news = _NewsAdapter()
    filings_client = SECEdgarFilings()
    filings_summary = _FilingsSummaryAdapter(filings_client)

    paper = EquityPaperTracker(equity_ledger, prices)

    alerts: TelegramAlerts | None = None
    if settings.telegram_bot_token:
        alerts = TelegramAlerts(settings.telegram_bot_token, settings.telegram_chat_id)

    # --- Mark-to-market and fire exits ---
    pre_mark = {pos["id"]: pos for pos in equity_ledger.open_positions()}
    exits = paper.mark_and_check_exits()
    if exits:
        print(f"\n=== {len(exits)} exit(s) fired ===")
        for ex in exits:
            print(f"  [{ex.position_id}] {ex.reason} @ {ex.exit_price:.2f}")
            if alerts is not None and ex.position_id in pre_mark:
                pos = pre_mark[ex.position_id]
                stats = equity_ledger.portfolio_stats()
                await alerts.send(alerts.format_equity_exit(
                    ex,
                    ticker=pos["ticker"],
                    entry_price=pos["entry_price"],
                    shares=pos["shares"],
                    portfolio_stats=stats,
                ))

    if mark_only:
        print("Mark-only mode complete.")
        if alerts is not None:
            await alerts.send(alerts.format_equity_portfolio(equity_ledger.portfolio_stats()))
        equity_ledger.close()
        fp_tracker.close()
        return

    # --- Swing screen ---
    calendar = YFinanceCalendar()
    event_screen = EventScreen(
        earnings=CalendarAdapter(calendar),
        filings=FilingsAdapter(filings_client),
    )
    swing_candidates = event_screen.scan(swing_universe)

    # --- Core screen ---
    fundamentals_provider = YFinanceFundamentals()
    quality_screen = QualityScreen(fundamentals_provider)
    core_candidates = quality_screen.scan(core_universe)

    print(f"\n=== Swing candidates: {len(swing_candidates)} ===")
    for c in swing_candidates:
        print(f"  [{c.event_type.value}] {c.instrument.ticker}: {c.evidence} (urgency={c.urgency:.2f})")

    print(f"\n=== Core candidates: {len(core_candidates)} ===")
    for c in core_candidates:
        print(f"  [{c.instrument.ticker}] score={c.score:.3f}: {c.evidence}")

    if no_analyse:
        print("Screen-only mode complete.")
        equity_ledger.close()
        fp_tracker.close()
        return

    # --- Scan summary alert ---
    if alerts is not None:
        analyst_count = min(len(swing_candidates), 5)
        await alerts.send(alerts.format_equity_scan(swing_candidates, core_candidates, analyst_count))

    # --- Analyst stage (uses Claude subscription via `claude -p`) ---
    budget = DailyBudget(daily_limit_usd=999.0)  # subscription: not per-token billed
    analyst = EquityAnalyst(
        llm=ClaudeCodeClient(),
        prices=prices,
        news=news,
        filings=filings_summary,
        budget=budget,
        max_candidates=5,
    )

    recommendations = analyst.analyse(swing_candidates)

    # --- Risk kernel + paper open ---
    kernel = RiskKernel(capital=settings.bankroll_usd)
    open_positions = equity_ledger.open_positions()

    print(f"\n=== Analyst recommendations: {len(recommendations)} ===")
    for rec in recommendations:
        sized = kernel.approve(rec, open_positions)
        if not sized.approved:
            print(f"  REJECTED [{rec.instrument.ticker}]: {sized.rejection_reason}")
            continue

        fill = paper.open_position(rec, sized.shares, rec.entry, strategy="equity_analyst")
        fp_tracker.record_entry(
            ticker=rec.instrument.ticker,
            sleeve=rec.sleeve.value,
            entry_price=rec.entry,
            shares=sized.shares,
            strategy="equity_analyst",
        )
        print(
            f"  PAPER OPEN [{rec.instrument.ticker}] "
            f"shares={sized.shares:.4f} entry={rec.entry:.2f} "
            f"stop={rec.stop_loss:.2f} tp={rec.take_profit:.2f}"
        )
        if alerts is not None:
            await alerts.send(alerts.format_equity_open(rec, fill))

    # --- Portfolio summary ---
    if alerts is not None:
        await alerts.send(alerts.format_equity_portfolio(equity_ledger.portfolio_stats()))

    print(f"\nBudget used today: ${budget.spent_today():.4f}")
    equity_ledger.close()
    fp_tracker.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Equities paper runner")
    parser.add_argument("--no-analyse", action="store_true", help="Screen only; skip Claude analyst")
    parser.add_argument("--mark-only", action="store_true", help="Mark-to-market + exits only")
    args = parser.parse_args()

    asyncio.run(
        run_once(
            DEFAULT_SWING_UNIVERSE,
            DEFAULT_CORE_UNIVERSE,
            no_analyse=args.no_analyse,
            mark_only=args.mark_only,
        )
    )


if __name__ == "__main__":
    main()
