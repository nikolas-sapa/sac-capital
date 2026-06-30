from __future__ import annotations

from datetime import date, timedelta

from core.assets.bar import Bar, PriceSeries
from equities.eval.report import build_report
from equities.eval.replay import ArtifactReplayEvaluator
from equities.research.artifacts import (
    Citation,
    EquityResearchArtifact,
    SourceRef,
    stable_hash,
)
from equities.research.store import ResearchArtifactStore


class FakePriceFeed:
    def __init__(self, series: dict[str, PriceSeries]) -> None:
        self._series = series

    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries:
        return self._series[ticker]


def _series(ticker: str, closes: list[float]) -> PriceSeries:
    start = date(2026, 1, 1)
    bars = [
        Bar(
            day=start + timedelta(days=idx),
            open=close,
            high=close * 1.02,
            low=close * 0.98,
            close=close,
            volume=1_000,
        )
        for idx, close in enumerate(closes)
    ]
    return PriceSeries(ticker=ticker, bars=bars)


def _artifact(
    ticker: str,
    as_of: str,
    sector: str,
    entry: float = 100.0,
    stop: float = 95.0,
    target: float = 110.0,
    decision: str = "approved",
) -> EquityResearchArtifact:
    payload = {
        "ticker": ticker,
        "as_of": as_of,
        "entry": entry,
        "stop": stop,
        "target": target,
    }
    return EquityResearchArtifact(
        artifact_id=stable_hash(payload),
        as_of=as_of,
        ticker=ticker,
        candidate={"ticker": ticker, "sector": sector},
        output_json={
            "action": "buy",
            "entry": entry,
            "stop_loss": stop,
            "take_profit": target,
            "confidence": 0.7,
        },
        decision=decision,  # type: ignore[arg-type]
    )


def test_replay_splits_train_validation_and_tracks_metrics():
    feed = FakePriceFeed({
        "WIN": _series("WIN", [100, 101, 104, 108, 112, 113]),
        "LOSS": _series("LOSS", [100, 99, 97, 94, 93, 92]),
        "VAL": _series("VAL", [100, 102, 104, 106, 111, 112]),
        "SPY": _series("SPY", [100, 100, 100, 100, 101, 101]),
    })
    artifacts = [
        _artifact("WIN", "2026-01-01T00:00:00+00:00", "Technology"),
        _artifact("LOSS", "2026-01-01T00:00:00+00:00", "Technology"),
        _artifact("VAL", "2026-01-03T00:00:00+00:00", "Industrials"),
    ]

    report = ArtifactReplayEvaluator(feed, holding_days=5, min_trades=1).evaluate(
        artifacts,
        validation_start=date(2026, 1, 3),
    )

    assert report.train.trade_count == 2
    assert report.train.win_rate == 0.5
    assert report.train.average_win_pct == 10.0
    assert report.train.average_loss_pct == -5.0
    assert report.train.profit_factor == 2.0
    assert report.train.median_return_pct == 2.5
    assert report.train.max_consecutive_losses == 1
    assert report.train.average_r_multiple == 0.5
    assert report.train.max_sector_concentration == 1.0
    assert report.validation.trade_count == 1
    assert report.validation.promotable is True
    assert report.validation.alpha_vs_benchmark_pct > 0
    assert report.validation.exit_distribution == {"target": 1}
    assert report.validation_trades[0].outcome == "target"
    assert "validation: trades=1" in report.to_text()
    assert "profit_factor=" in report.to_text()


def test_replay_ignores_rejected_artifacts_and_blocks_small_samples():
    feed = FakePriceFeed({
        "WIN": _series("WIN", [100, 101, 104, 108, 112, 113]),
        "REJ": _series("REJ", [100, 101, 104, 108, 112, 113]),
    })
    artifacts = [
        _artifact("WIN", "2026-01-01T00:00:00+00:00", "Technology"),
        _artifact("REJ", "2026-01-01T00:00:00+00:00", "Technology", decision="rejected"),
    ]

    report = ArtifactReplayEvaluator(feed, holding_days=5, min_trades=3).evaluate(
        artifacts,
        validation_start=date(2026, 1, 1),
    )

    assert report.train.trade_count == 0
    assert report.validation.trade_count == 1
    assert report.validation.promotable is False
    assert report.validation.rejection_reason == "sample_size_below_min_trades=3"


def test_replay_missing_benchmark_data_does_not_fail():
    feed = FakePriceFeed({
        "WIN": _series("WIN", [100, 101, 104, 108, 112, 113]),
    })
    artifacts = [_artifact("WIN", "2026-01-01T00:00:00+00:00", "Technology")]

    report = ArtifactReplayEvaluator(feed, holding_days=5, min_trades=1).evaluate(
        artifacts,
        validation_start=date(2026, 1, 1),
    )

    assert report.validation.trade_count == 1
    assert report.validation.alpha_vs_benchmark_pct == 0.0
    assert report.validation.beta_vs_benchmark == 0.0


def test_report_command_builder_reads_artifact_store(tmp_path):
    store = ResearchArtifactStore(tmp_path / "research_artifacts.jsonl")
    store.append(_artifact("WIN", "2026-01-01T00:00:00+00:00", "Technology"))
    feed = FakePriceFeed({"WIN": _series("WIN", [100, 101, 104, 108, 112, 113])})

    text = build_report(
        str(store.path),
        validation_start=date(2026, 1, 1),
        holding_days=5,
        min_trades=1,
        prices=feed,
    )

    assert "Equity artifact replay report" in text
    assert "validation: trades=1" in text
    assert "promotable=True" in text


def test_report_includes_citation_attribution_section(tmp_path):
    artifact = _artifact("WIN", "2026-01-01T00:00:00+00:00", "Technology")
    artifact.sources.append(
        SourceRef(id="src-1", kind="news", source="Reuters")
    )
    artifact.citations.append(
        Citation(source_ref_id="src-1", quote_or_summary="bullish outlook")
    )
    store = ResearchArtifactStore(tmp_path / "research_artifacts.jsonl")
    store.append(artifact)
    feed = FakePriceFeed({"WIN": _series("WIN", [100, 101, 104, 108, 112, 113])})

    text = build_report(
        str(store.path),
        validation_start=date(2026, 1, 1),
        holding_days=5,
        min_trades=1,
        prices=feed,
    )

    assert "Citation attribution by source:" in text
    assert "Reuters: trades=1" in text
