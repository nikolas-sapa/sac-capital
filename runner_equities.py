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

from core.assets.instrument import CapTier, Instrument
from core.config import load_config
from equities.analysis.analyst import EquityAnalyst, AnthropicLLMClient
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
    Instrument("ARWR",  "Arrowhead Pharmaceuticals", "NASDAQ", CapTier.MID),
    Instrument("PRCT",  "PROCEPT BioRobotics",       "NASDAQ", CapTier.MID),
    Instrument("PGNY",  "Progyny",                    "NASDAQ", CapTier.MID),
    Instrument("SMCI",  "Super Micro Computer",       "NASDAQ", CapTier.MID),
    Instrument("FIGS",  "FIGS",                       "NYSE",   CapTier.MID),
    Instrument("XPEL",  "XPEL",                       "NASDAQ", CapTier.SMALL),
    Instrument("KLIC",  "Kulicke and Soffa",          "NASDAQ", CapTier.MID),
]

DEFAULT_CORE_UNIVERSE: list[Instrument] = [
    Instrument("MSFT",  "Microsoft",       "NASDAQ", CapTier.LARGE),
    Instrument("AAPL",  "Apple",           "NASDAQ", CapTier.LARGE),
    Instrument("GOOGL", "Alphabet",        "NASDAQ", CapTier.LARGE),
    Instrument("META",  "Meta Platforms",  "NASDAQ", CapTier.LARGE),
    Instrument("V",     "Visa",            "NYSE",   CapTier.LARGE),
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
            return series.latest if series.bars else None
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

    # --- Mark-to-market and fire exits ---
    exits = paper.mark_and_check_exits()
    if exits:
        print(f"\n=== {len(exits)} exit(s) fired ===")
        for ex in exits:
            print(f"  [{ex.position_id}] {ex.reason} @ {ex.exit_price:.2f}")

    if mark_only:
        print("Mark-only mode complete.")
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

    if no_analyse or not settings.anthropic_api_key:
        if not settings.anthropic_api_key:
            print("\n[!] ANTHROPIC_API_KEY not set — skipping analyst stage.")
        print("Screen-only mode complete.")
        equity_ledger.close()
        fp_tracker.close()
        return

    # --- Analyst stage ---
    llm_client = AnthropicLLMClient(settings.anthropic_api_key)
    budget = DailyBudget(daily_limit_usd=1.0)
    analyst = EquityAnalyst(
        llm=llm_client,
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
