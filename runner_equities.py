"""Equities runner — screen → analyse → risk-gate → paper-open → nightly mark.

Usage:
    uv run python runner_equities.py                    # single pass
    uv run python runner_equities.py --no-analyse       # screen only (no Claude API)
    uv run python runner_equities.py --mark-only        # mark-to-market + exit check

Uses Claude Code subscription (claude -p) — no ANTHROPIC_API_KEY required.
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
from equities.analysis.core_analyst import CoreDCAAnalyst
from equities.data.news import YFinanceNewsProvider
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
    # Semiconductor equipment & packaging
    Instrument("KLIC",  "Kulicke and Soffa",          "NASDAQ", CapTier.MID),
    Instrument("ONTO",  "Onto Innovation",            "NYSE",   CapTier.MID),
    Instrument("LRCX",  "Lam Research",               "NASDAQ", CapTier.LARGE),
    Instrument("KLAC",  "KLA Corporation",            "NASDAQ", CapTier.LARGE),
    Instrument("ENTG",  "Entegris",                   "NASDAQ", CapTier.MID),
    Instrument("AMKR",  "Amkor Technology",           "NASDAQ", CapTier.MID),
    # AI chips & semiconductor infrastructure
    Instrument("AMD",   "Advanced Micro Devices",     "NASDAQ", CapTier.LARGE),
    Instrument("MU",    "Micron Technology",          "NASDAQ", CapTier.LARGE),
    Instrument("MRVL",  "Marvell Technology",         "NASDAQ", CapTier.MID),
    Instrument("ALAB",  "Astera Labs",                "NASDAQ", CapTier.SMALL),
    Instrument("NBIS",  "Nebius Group",               "NASDAQ", CapTier.SMALL),
    Instrument("QCOM",  "Qualcomm",                   "NASDAQ", CapTier.LARGE),
    Instrument("SMCI",  "Super Micro Computer",       "NASDAQ", CapTier.MID),
    # Optical / connectivity (NVIDIA supply chain)
    Instrument("COHR",  "Coherent Corp",              "NYSE",   CapTier.MID),
    Instrument("LITE",  "Lumentum Holdings",          "NASDAQ", CapTier.MID),
    Instrument("AAOI",  "Applied Optoelectronics",    "NASDAQ", CapTier.SMALL),
    Instrument("FN",    "Fabrinet",                   "NYSE",   CapTier.MID),
    Instrument("APH",   "Amphenol",                   "NYSE",   CapTier.LARGE),
    Instrument("AXTI",  "AXT Inc",                    "NASDAQ", CapTier.SMALL),
    Instrument("VIAV",  "VIAVI Solutions",            "NASDAQ", CapTier.MID),
    # AI server ODM / construction
    Instrument("CLS",   "Celestica",                  "NYSE",   CapTier.MID),
    Instrument("FIX",   "Comfort Systems USA",        "NYSE",   CapTier.MID),
    # Power grid & nuclear
    Instrument("CEG",   "Constellation Energy",       "NASDAQ", CapTier.LARGE),
    Instrument("GEV",   "GE Vernova",                 "NYSE",   CapTier.LARGE),
    Instrument("ETN",   "Eaton Corporation",          "NYSE",   CapTier.LARGE),
    Instrument("PWR",   "Quanta Services",            "NYSE",   CapTier.LARGE),
    Instrument("VRT",   "Vertiv Holdings",            "NYSE",   CapTier.MID),
    # High-growth / catalyst plays
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
    Instrument("SQ",    "Block",                      "NYSE",   CapTier.MID),
    Instrument("AFRM",  "Affirm",                     "NASDAQ", CapTier.MID),
    Instrument("NU",    "Nu Holdings",                "NYSE",   CapTier.MID),
    Instrument("TSLA",  "Tesla",                      "NASDAQ", CapTier.LARGE),
    Instrument("ARM",   "Arm Holdings",               "NASDAQ", CapTier.LARGE),
    Instrument("CVNA",  "Carvana",                    "NYSE",   CapTier.MID),
    Instrument("RBRK",  "Rubrik",                     "NYSE",   CapTier.MID),
    Instrument("SOUN",  "SoundHound AI",              "NASDAQ", CapTier.SMALL),
    Instrument("XPEL",  "XPEL",                       "NASDAQ", CapTier.SMALL),
    # Cybersecurity
    Instrument("ZS",    "Zscaler",                    "NASDAQ", CapTier.MID),
    Instrument("S",     "SentinelOne",                "NYSE",   CapTier.MID),
    Instrument("PANW",  "Palo Alto Networks",         "NASDAQ", CapTier.LARGE),
    Instrument("FTNT",  "Fortinet",                   "NASDAQ", CapTier.LARGE),
    Instrument("CYBR",  "CyberArk Software",          "NASDAQ", CapTier.MID),
    # Cloud / AI SaaS
    Instrument("NOW",   "ServiceNow",                 "NYSE",   CapTier.LARGE),
    Instrument("CRM",   "Salesforce",                 "NYSE",   CapTier.LARGE),
    Instrument("MNDY",  "Monday.com",                 "NASDAQ", CapTier.MID),
    Instrument("HUBS",  "HubSpot",                    "NYSE",   CapTier.MID),
    Instrument("MDB",   "MongoDB",                    "NASDAQ", CapTier.MID),
    Instrument("TTD",   "The Trade Desk",             "NASDAQ", CapTier.MID),
    Instrument("CFLT",  "Confluent",                  "NASDAQ", CapTier.MID),
    Instrument("VEEV",  "Veeva Systems",              "NYSE",   CapTier.LARGE),
    # E-commerce / consumer tech
    Instrument("SHOP",  "Shopify",                    "NYSE",   CapTier.LARGE),
    Instrument("MELI",  "MercadoLibre",               "NASDAQ", CapTier.LARGE),
    Instrument("TOST",  "Toast",                      "NYSE",   CapTier.MID),
    Instrument("GLBE",  "Global-E Online",            "NASDAQ", CapTier.SMALL),
    Instrument("UBER",  "Uber",                       "NYSE",   CapTier.LARGE),
    Instrument("PYPL",  "PayPal",                     "NASDAQ", CapTier.LARGE),
    Instrument("FOUR",  "Shift4 Payments",            "NYSE",   CapTier.MID),
    # Defense / space
    Instrument("KTOS",  "Kratos Defense",             "NASDAQ", CapTier.MID),
    Instrument("AVAV",  "AeroVironment",              "NASDAQ", CapTier.MID),
    Instrument("ASTS",  "AST SpaceMobile",            "NASDAQ", CapTier.SMALL),
    Instrument("LUNR",  "Intuitive Machines",         "NASDAQ", CapTier.SMALL),
    # Healthcare AI / consumer growth
    Instrument("TEM",   "Tempus AI",                  "NASDAQ", CapTier.MID),
    Instrument("GEHC",  "GE HealthCare",              "NASDAQ", CapTier.LARGE),
    Instrument("DOCS",  "Doximity",                   "NYSE",   CapTier.MID),
    Instrument("HIMS",  "Hims & Hers",                "NYSE",   CapTier.SMALL),
    Instrument("DUOL",  "Duolingo",                   "NASDAQ", CapTier.MID),
    Instrument("ONON",  "On Holding",                 "NYSE",   CapTier.MID),
    Instrument("DKNG",  "DraftKings",                 "NASDAQ", CapTier.MID),
    # Market laggards / re-rating plays
    Instrument("ADBE",  "Adobe",                      "NASDAQ", CapTier.LARGE),
    Instrument("VST",   "Vistra Energy",              "NYSE",   CapTier.LARGE),
    Instrument("TDC",   "Teradata",                   "NYSE",   CapTier.MID),
    Instrument("PGY",   "Pagaya Technologies",        "NASDAQ", CapTier.SMALL),
    Instrument("JBL",   "Jabil",                      "NYSE",   CapTier.LARGE),
    # Edge AI / robotics
    Instrument("AMBA",  "Ambarella",                  "NASDAQ", CapTier.SMALL),
    Instrument("PRCT",  "PROCEPT BioRobotics",        "NASDAQ", CapTier.MID),
    # Inference / new IPOs
    Instrument("CRBR",  "Cerebras Systems",           "NASDAQ", CapTier.MID),
    Instrument("AI",    "C3.ai",                      "NYSE",   CapTier.SMALL),
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
    Instrument("COST",  "Costco",          "NASDAQ", CapTier.LARGE),
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
    news = YFinanceNewsProvider()
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

    swing_recommendations = analyst.analyse(swing_candidates)

    # --- Core DCA analyst (risk-officer check before accumulating) ---
    core_analyst = CoreDCAAnalyst(
        llm=ClaudeCodeClient(),
        prices=prices,
        news=news,
        budget=budget,
        max_candidates=4,
    )
    core_recommendations = core_analyst.analyse(core_candidates)

    all_recommendations = swing_recommendations + core_recommendations

    # --- Risk kernel + paper open ---
    kernel = RiskKernel(capital=settings.bankroll_usd)
    open_positions = equity_ledger.open_positions()

    print(f"\n=== Swing recommendations: {len(swing_recommendations)} ===")
    print(f"=== Core DCA recommendations: {len(core_recommendations)} ===")
    for rec in all_recommendations:
        sized = kernel.approve(rec, open_positions)
        if not sized.approved:
            print(f"  REJECTED [{rec.instrument.ticker}] ({rec.sleeve.value}): {sized.rejection_reason}")
            continue

        fill = paper.open_position(rec, sized.shares, rec.entry, strategy="equity_analyst")
        fp_tracker.record_entry(
            ticker=rec.instrument.ticker,
            sleeve=rec.sleeve.value,
            entry_price=rec.entry,
            shares=sized.shares,
            strategy="equity_analyst",
        )
        if rec.sleeve.value == "core":
            print(
                f"  DCA OPEN [{rec.instrument.ticker}] "
                f"shares={sized.shares:.4f} entry={rec.entry:.2f} (no stop)"
            )
        else:
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
