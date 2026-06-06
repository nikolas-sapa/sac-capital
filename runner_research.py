"""Weekly research runner — mines supply chain theses and scores discovery lags.

Usage:
    uv run python runner_research.py

Writes top 50 research candidates to data/research_candidates.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from equities.research.discovery_lag import DiscoveryLagCalculator
from equities.research.supply_chain import SUPPLY_CHAIN, BottleneckScorer
from equities.research.thesis_miner import ThesisMiner


def main() -> None:
    Path("data").mkdir(exist_ok=True)
    miner = ThesisMiner()
    lag = DiscoveryLagCalculator()
    scorer = BottleneckScorer()

    print("=== ThesisMiner ===\n")
    all_candidates: list[dict] = []
    for result in miner.mine_all():
        print(f"Thesis: {result.thesis[:80]}...")
        print(f"  Trunk={result.trunk}  L1={result.level_1}  L2={result.level_2}  L3={result.level_3}")
        for level, tickers in [("L1", result.level_1), ("L2", result.level_2), ("L3", result.level_3)]:
            for ticker in tickers:
                d_lag = lag.compute(result.trunk, ticker)
                b_score = scorer.score(ticker, result.trunk)
                all_candidates.append({
                    "ticker": ticker,
                    "trunk": result.trunk,
                    "level": level,
                    "discovery_lag_pct": d_lag,
                    "bottleneck_score": b_score,
                    "opportunity_score": round((d_lag / 100) * b_score, 4),
                    "thesis": result.thesis[:100],
                })

    print("\n=== Static supply chain discovery lag (top 4 trunks) ===")
    for trunk in list(SUPPLY_CHAIN.keys())[:4]:
        print(f"\n{trunk}:")
        for leaf, b, d in lag.score_all_leaves(trunk)[:5]:
            print(f"  {leaf}  bottleneck={b:.2f}  lag={d:+.1f}pp")
            all_candidates.append({
                "ticker": leaf,
                "trunk": trunk,
                "level": "static",
                "discovery_lag_pct": d,
                "bottleneck_score": b,
                "opportunity_score": round((max(d, 0.0) / 100) * b, 4),
                "thesis": f"Static supply-chain lag behind {trunk}",
            })

    all_candidates.sort(key=lambda x: x["opportunity_score"], reverse=True)
    out = Path("data/research_candidates.json")
    out.write_text(json.dumps(all_candidates[:50], indent=2))
    print(f"\nTop 50 saved to {out}")


if __name__ == "__main__":
    main()
