"""Weekly research runner — mines supply chain theses and scores discovery lags.

Usage:
    uv run python runner_research.py

Writes top 50 research candidates to data/research_candidates.json.
"""
from __future__ import annotations

import json
import argparse
from pathlib import Path

from equities.research.discovery_lag import DiscoveryLagCalculator
from equities.research.supply_chain import SUPPLY_CHAIN, BottleneckScorer
from equities.research.thesis_miner import ThesisMiner


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Skip LLM thesis mining and refresh static supply-chain lag candidates only.",
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
    out = Path("data/research_candidates.json")
    if all_candidates and all(c["opportunity_score"] == 0.0 for c in all_candidates):
        if out.exists():
            raise RuntimeError(
                "all research opportunity scores are zero; refusing to overwrite existing candidates"
            )
    out.write_text(json.dumps(all_candidates[:50], indent=2))
    print(f"\nTop 50 saved to {out}")


if __name__ == "__main__":
    main()
