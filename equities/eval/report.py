from __future__ import annotations

import argparse
from datetime import date

from equities.data.prices import YFinancePriceFeed
from equities.eval.replay import ArtifactReplayEvaluator, HistoryProvider
from equities.research.store import ResearchArtifactStore


def build_report(
    artifact_path: str,
    validation_start: date,
    *,
    holding_days: int = 20,
    min_trades: int = 20,
    prices: HistoryProvider | None = None,
) -> str:
    store = ResearchArtifactStore(artifact_path)
    evaluator = ArtifactReplayEvaluator(
        prices or YFinancePriceFeed(),
        holding_days=holding_days,
        min_trades=min_trades,
    )
    report = evaluator.evaluate(store.read_all(), validation_start=validation_start)
    return report.to_text()


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay equity research artifacts against prices")
    parser.add_argument("--artifacts", default="data/research_artifacts.jsonl")
    parser.add_argument("--validation-start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--holding-days", type=int, default=20)
    parser.add_argument("--min-trades", type=int, default=20)
    args = parser.parse_args()

    print(
        build_report(
            args.artifacts,
            date.fromisoformat(args.validation_start),
            holding_days=args.holding_days,
            min_trades=args.min_trades,
        )
    )


if __name__ == "__main__":
    main()
