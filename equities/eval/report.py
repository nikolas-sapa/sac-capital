from __future__ import annotations

import argparse
from datetime import date

from equities.data.prices import YFinancePriceFeed
from equities.eval.citation_attribution import SourceAttribution, attribute_returns_by_source
from equities.eval.replay import ArtifactReplayEvaluator, HistoryProvider
from equities.research.store import ResearchArtifactStore


def _format_citation_attribution(attribution: dict[str, SourceAttribution]) -> str:
    if not attribution:
        return ""
    lines = ["", "Citation attribution by source:"]
    for source, stats in sorted(attribution.items()):
        lines.append(
            f"  {source}: trades={stats.trade_count} "
            f"expectancy={stats.expectancy_pct:+.2f}% win_rate={stats.win_rate:.2%}"
        )
    return "\n".join(lines)


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
    artifacts = store.read_all()
    report = evaluator.evaluate(artifacts, validation_start=validation_start)
    attribution = attribute_returns_by_source(
        artifacts, report.train_trades + report.validation_trades
    )
    return report.to_text() + _format_citation_attribution(attribution)


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
