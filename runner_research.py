"""Weekly research runner — mines supply chain theses and scores discovery lags.

Usage:
    uv run python runner_research.py

Writes top 50 research candidates to data/research_candidates.json.
"""
from __future__ import annotations

import json
import argparse
from dataclasses import asdict
from pathlib import Path

from equities.research.backtest import append_backtest_report, run_backtest
from equities.research.discovery_lag import DiscoveryLagCalculator
from equities.research.supply_chain import SUPPLY_CHAIN, BottleneckScorer
from equities.research.thesis_miner import ThesisMiner
from equities.screen.supply_chain_lag_screen import SupplyChainLagScreen


def opportunity_score(*, lag_1y: float, lag_3mo: float, lag_1mo: float, bottleneck: float) -> float:
    """Score delayed supplier catch-up across slow and fresh windows."""
    positive_lag = (
        max(lag_1y, 0.0) * 0.35
        + max(lag_3mo, 0.0) * 0.40
        + max(lag_1mo, 0.0) * 0.25
    )
    return round((positive_lag / 100) * bottleneck, 4)


def _candidate_payload(
    *,
    ticker: str,
    trunk: str,
    level: str,
    lag: DiscoveryLagCalculator,
    bottleneck_score: float,
    thesis: str,
) -> dict:
    lag_1y = lag.compute(trunk, ticker, period="1y")
    lag_3mo = lag.compute(trunk, ticker, period="3mo")
    lag_1mo = lag.compute(trunk, ticker, period="1mo")
    return {
        "ticker": ticker,
        "trunk": trunk,
        "level": level,
        "discovery_lag_pct": lag_1y,
        "discovery_lag_3mo_pct": lag_3mo,
        "discovery_lag_1mo_pct": lag_1mo,
        "bottleneck_score": bottleneck_score,
        "opportunity_score": opportunity_score(
            lag_1y=lag_1y,
            lag_3mo=lag_3mo,
            lag_1mo=lag_1mo,
            bottleneck=bottleneck_score,
        ),
        "thesis": thesis,
    }


def _candidate_score(candidate: dict) -> float:
    value = candidate.get("opportunity_score", 0.0)
    return float(value) if isinstance(value, int | float) else 0.0


def _strategy_candidate_payload(candidate) -> dict:
    payload = asdict(candidate)
    payload["opportunity_score"] = candidate.opportunity_score
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Skip LLM thesis mining and refresh static supply-chain lag candidates only.",
    )
    parser.add_argument(
        "--strategy-backtest",
        action="store_true",
        help="Generate top-3 lagged supplier strategy candidates and append a paper backtest report.",
    )
    args = parser.parse_args()

    Path("data").mkdir(exist_ok=True)
    lag = DiscoveryLagCalculator()
    scorer = BottleneckScorer()

    all_candidates: list[dict] = []
    if not args.static_only:
        miner = ThesisMiner()
        print("=== ThesisMiner ===\n")
        for result in miner.mine_all():
            print(f"Thesis: {result.thesis[:80]}...")
            print(f"  Trunk={result.trunk}  L1={result.level_1}  L2={result.level_2}  L3={result.level_3}")
            for level, tickers in [("L1", result.level_1), ("L2", result.level_2), ("L3", result.level_3)]:
                for ticker in tickers:
                    b_score = scorer.score(ticker, result.trunk)
                    all_candidates.append(_candidate_payload(
                        ticker=ticker,
                        trunk=result.trunk,
                        level=level,
                        lag=lag,
                        bottleneck_score=b_score,
                        thesis=result.thesis[:100],
                    ))
    else:
        print("=== Static-only supply chain discovery lag ===")

    print("\n=== Static supply chain discovery lag (top 4 trunks) ===")
    for trunk in list(SUPPLY_CHAIN.keys())[:4]:
        print(f"\n{trunk}:")
        for leaf, b, d in lag.score_all_leaves(trunk)[:8]:
            print(f"  {leaf}  bottleneck={b:.2f}  lag={d:+.1f}pp")
            all_candidates.append(_candidate_payload(
                ticker=leaf,
                trunk=trunk,
                level="static",
                lag=lag,
                bottleneck_score=b,
                thesis=f"Static supply-chain lag behind {trunk}",
            ))

    all_candidates.sort(key=lambda x: x["opportunity_score"], reverse=True)

    if args.strategy_backtest:
        from equities.data.prices import YFinancePriceFeed

        print("\n=== Lagged supplier strategy backtest ===")
        price_feed = YFinancePriceFeed()
        strategy_screen = SupplyChainLagScreen(price_feed)
        strategy_candidates = strategy_screen.scan()
        print(f"Strategy candidates: {len(strategy_candidates)}")
        for candidate in strategy_candidates[:10]:
            print(
                f"  [{candidate.strategy}] {candidate.ticker} via {candidate.trunk} "
                f"score={candidate.opportunity_score:.4f}"
            )
        all_candidates.extend(_strategy_candidate_payload(candidate) for candidate in strategy_candidates)
        report = run_backtest(strategy_candidates, price_feed)
        append_backtest_report(Path("data/strategy_backtests.jsonl"), report)
        print(
            "Backtest: "
            f"trades={report.trade_count} expectancy={report.expectancy_pct:+.2f}% "
            f"hit_rate={report.hit_rate:.0%} profit_factor={report.profit_factor:.2f} "
            f"max_dd={report.max_drawdown_pct:+.2f}%"
        )
        print(f"Backtest report appended to data/strategy_backtests.jsonl")

    all_candidates.sort(key=_candidate_score, reverse=True)
    out = Path("data/research_candidates.json")
    if all_candidates and all(_candidate_score(c) == 0.0 for c in all_candidates):
        if out.exists():
            raise RuntimeError(
                "all research opportunity scores are zero; refusing to overwrite existing candidates"
            )
    out.write_text(json.dumps(all_candidates[:50], indent=2))
    print(f"\nTop 50 saved to {out}")


if __name__ == "__main__":
    main()
