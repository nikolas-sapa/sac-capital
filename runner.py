"""End-to-end paper-trading runner for the Polymarket bot.

GEO-BLOCK NOTE
--------------
The live run is BLOCKED on this machine due to Polymarket's geo-restriction.
Connect via VPN to a non-restricted region before running.

Usage
-----
    uv run python runner.py                       # simple mode, dummy strategy
    uv run python runner.py --strategy dummy      # explicit
    uv run python runner.py --strategy dummy,foo  # comma-separated
    uv run python runner.py --mode orchestrated   # performance-weighted multi-strategy
"""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
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
from strategies.llm_probability.strategy import LLMProbabilityStrategy
from strategies.weather.strategy import WeatherStrategy
from strategies.crypto_updown.strategy import CryptoUpDownStrategy

# ---------------------------------------------------------------------------
# Strategy registry  (name → class)
# ---------------------------------------------------------------------------

STRATEGIES: dict[str, type] = {
    "dummy": DummyStrategy,
    "llm": LLMProbabilityStrategy,
    "weather": WeatherStrategy,
    "crypto_updown": CryptoUpDownStrategy,
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
            ledger = getattr(executor, "_ledger", None)
            if ledger is not None and ledger.has_open_position(
                signal.market.condition_id,
                signal.token_id,
            ):
                continue

            frac = kelly_fraction(signal.fair_prob, signal.price, frac=settings.kelly_fraction)
            if frac <= 0:
                continue  # no edge — skip, don't force a trade

            stake = frac * settings.bankroll_usd
            cap = settings.max_position_pct * settings.bankroll_usd
            stake = min(stake, cap)  # HARD CAP: no single position > MAX_POSITION_PCT

            fill = executor.place(signal, stake, strategy=strategy.name)
            results.append(fill)

            if alerts is not None:
                await alerts.send(alerts.format_fill(fill))

    return results


async def run_orchestrated(
    markets: list[Market],
    strategies: list[Strategy],
    executor: Executor,
    settings: Settings,
    ledger: Ledger,
    alerts: TelegramAlerts | None = None,
) -> list[Fill]:
    """Orchestrated pass: collect → reconcile → allocate → size → risk-gate → execute.

    Replaces run_once() when --mode orchestrated is selected. Uses per-strategy
    performance stats from the ledger to weight capital allocation, and applies
    portfolio-level risk limits before execution.
    """
    from orchestrator.allocator import allocate
    from orchestrator.performance import StrategyStats
    from orchestrator.reconcile import reconcile
    from orchestrator.risk import RiskGate, SizedSignal

    # 1. Collect signals from all strategies, track which strategy each came from
    all_signals = []
    signal_strategy: dict[int, str] = {}  # id(signal) → strategy name
    for strategy in strategies:
        for sig in strategy.scan(markets):
            signal_strategy[id(sig)] = strategy.name
            all_signals.append(sig)

    # 2. Reconcile conflicts (deduplicate same-market signals, drop opposing)
    reconciled = reconcile(all_signals)

    # 3. Get per-strategy rolling stats, compute budgets
    stats_engine = StrategyStats(ledger)
    stats = {s.name: stats_engine.rolling(s.name) for s in strategies}
    budgets = allocate(settings.bankroll_usd, stats)
    strategy_spend: dict[str, float] = defaultdict(float)

    # 4. Size via Kelly within per-strategy budget
    sized: list[SizedSignal] = []
    for sig in reconciled:
        strat_name = signal_strategy.get(id(sig), "unknown")
        budget = budgets.get(strat_name, 0.0)

        frac = kelly_fraction(sig.fair_prob, sig.price, frac=settings.kelly_fraction)
        if frac <= 0:
            continue

        stake = frac * settings.bankroll_usd
        cap = settings.max_position_pct * settings.bankroll_usd
        remaining_budget = budget - strategy_spend[strat_name]
        stake = min(stake, cap, remaining_budget)

        if stake <= 0:
            continue

        sized.append(SizedSignal(signal=sig, strategy=strat_name, stake=stake))
        strategy_spend[strat_name] += stake

    # 5. Portfolio risk gate
    gate = RiskGate(ledger)
    approved = gate.approve(sized, settings.bankroll_usd)

    # 6. Execute and notify
    results: list[Fill] = []
    for ss in approved:
        if ledger.has_open_position(ss.signal.market.condition_id, ss.signal.token_id):
            continue
        fill = executor.place(ss.signal, ss.stake, strategy=ss.strategy)
        results.append(fill)
        if alerts is not None:
            await alerts.send(alerts.format_fill(fill))

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def main(strategy_names: list[str], mode: str = "simple") -> None:
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
        markets = await fetch_markets(limit=500)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to fetch markets (geo-blocked? check VPN/region): {exc}"
        ) from exc

    # Ledger — ensure data/ dir exists
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    with Ledger(data_dir / "ledger.db") as ledger:
        executor = PaperExecutor(ledger)

        # Telegram alerts only if token is configured
        alerts: TelegramAlerts | None = None
        if settings.telegram_bot_token:
            alerts = TelegramAlerts(settings.telegram_bot_token, settings.telegram_chat_id)

        if alerts is not None and settings.polymarket_scan_alerts:
            await alerts.send(alerts.format_polymarket_scan(len(markets), [s.name for s in strategies]))

        if mode == "orchestrated":
            fills = await run_orchestrated(markets, strategies, executor, settings, ledger, alerts)
        else:
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
    parser.add_argument(
        "--mode",
        choices=["simple", "orchestrated"],
        default="simple",
        help="simple: flat Kelly per signal; orchestrated: performance-weighted with risk gate",
    )
    args = parser.parse_args()

    # Flatten repeated + comma-separated values, default to ["dummy"]
    raw: list[str] = args.strategies or ["dummy"]
    names: list[str] = []
    for item in raw:
        names.extend(n.strip() for n in item.split(",") if n.strip())

    asyncio.run(main(names, mode=args.mode))
