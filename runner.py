"""End-to-end paper-trading runner for the Polymarket bot (Task 12).

GEO-BLOCK NOTE
--------------
Step 5 (live run with --strategy dummy against Polymarket's gamma API) is
BLOCKED on this machine due to Polymarket's geo-restriction. The CLI is
fully implemented; to run it manually, connect via VPN to a non-restricted
region and execute:

    uv run python runner.py --strategy dummy

The gamma API call in main() will raise an httpx error when geo-blocked.
All offline tests (tests/test_runner.py) pass without network access.

Usage
-----
    uv run python runner.py                       # runs "dummy" strategy
    uv run python runner.py --strategy dummy      # explicit
    uv run python runner.py --strategy dummy,foo  # comma-separated
    uv run python runner.py --strategy dummy --strategy foo  # repeatable
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from core.alerts.telegram import TelegramAlerts
from core.clob.rest import fetch_markets
from core.config import Settings, load_config
from core.execution.base import Executor, Fill
from core.execution.paper import PaperExecutor
from core.ledger import Ledger
from core.markets import Market
from core.sizing.kelly import kelly_fraction
from core.strategy import Strategy
from strategies.dummy import DummyStrategy

# ---------------------------------------------------------------------------
# Strategy registry  (name → class)
# ---------------------------------------------------------------------------

STRATEGIES: dict[str, type] = {
    "dummy": DummyStrategy,
}


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

async def run_once(
    markets: list[Market],
    strategies: list[Strategy],
    executor: Executor,
    settings: Settings,
    alerts: TelegramAlerts | None = None,
) -> list[Fill]:
    """Execute one scan-and-place pass across all strategies.

    For each strategy, call strategy.scan(markets). For each signal:
      1. Size via fractional Kelly; skip if fraction <= 0 (no edge).
      2. Cap stake at max_position_pct * bankroll_usd.
      3. Place via executor; record fill.
      4. Send Telegram alert (if alerts is not None).

    Args:
        markets:    List of Market objects to scan.
        strategies: List of Strategy instances to run.
        executor:   Executor (paper or live) implementing place(signal, stake) -> Fill.
        settings:   Settings object with .bankroll_usd, .kelly_fraction, .max_position_pct.
        alerts:     Optional TelegramAlerts (or compatible); send called per fill.

    Returns:
        List of Fill objects produced this pass.
    """
    results: list[Fill] = []

    for strategy in strategies:
        signals = strategy.scan(markets)
        for signal in signals:
            frac = kelly_fraction(signal.fair_prob, signal.price, frac=settings.kelly_fraction)
            if frac <= 0:
                continue  # no edge — skip, don't force a trade

            stake = frac * settings.bankroll_usd
            cap = settings.max_position_pct * settings.bankroll_usd
            stake = min(stake, cap)  # HARD CAP: no single position > MAX_POSITION_PCT

            fill = executor.place(signal, stake)
            results.append(fill)

            if alerts is not None:
                await alerts.send(alerts.format_fill(fill))

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def main(strategy_names: list[str]) -> None:
    """Load config, build components, run one pass, print summary.

    Telegram alerts are only built when a bot token is configured — otherwise
    alerts=None and the runner operates silently.
    """
    settings = load_config()

    # Build strategy instances from registry
    strategies = []
    for name in strategy_names:
        if name not in STRATEGIES:
            raise ValueError(f"Unknown strategy: {name!r}. Available: {list(STRATEGIES)}")
        strategies.append(STRATEGIES[name]())

    # Fetch markets (requires network; geo-blocked on this machine without VPN)
    try:
        markets = await fetch_markets(limit=20)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to fetch markets (geo-blocked? check VPN/region): {exc}"
        ) from exc

    # Ledger — ensure data/ dir exists
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    ledger = Ledger(data_dir / "ledger.db")

    executor = PaperExecutor(ledger)

    # Telegram alerts only if token is configured
    alerts: TelegramAlerts | None = None
    if settings.telegram_bot_token:
        alerts = TelegramAlerts(settings.telegram_bot_token, settings.telegram_chat_id)

    fills = await run_once(markets, strategies, executor, settings, alerts)

    # Summary
    print(f"\n=== Run complete: {len(fills)} fill(s) ===")
    for fill in fills:
        try:
            label = fill.signal.market.outcome_by_token(fill.signal.token_id).label
        except KeyError:
            label = fill.signal.token_id
        print(
            f"  [{fill.signal.market.condition_id}] {fill.signal.market.question[:60]}"
            f" | {label} | stake={fill.stake:.2f} | price={fill.avg_price:.4f}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Polymarket paper-trading runner (Task 12).\n\n"
        "NOTE: Polymarket is geo-blocked on this machine without VPN. "
        "Connect via VPN before running.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--strategy",
        dest="strategies",
        action="append",
        default=None,
        metavar="NAME",
        help=(
            "Strategy name(s) to run. Repeatable or comma-separated. "
            "Defaults to 'dummy'. Available: " + ", ".join(STRATEGIES)
        ),
    )
    args = parser.parse_args()

    # Flatten repeated + comma-separated values, default to ["dummy"]
    raw: list[str] = args.strategies or ["dummy"]
    names: list[str] = []
    for item in raw:
        names.extend(n.strip() for n in item.split(",") if n.strip())

    asyncio.run(main(names))
