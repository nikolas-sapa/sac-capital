from __future__ import annotations

from datetime import date

from equities.eval.citation_attribution import attribute_returns_by_source
from equities.eval.replay import ReplayTrade
from equities.research.artifacts import Citation, EquityResearchArtifact, SourceRef


def _artifact(
    artifact_id: str,
    sources: list[SourceRef] | None = None,
    citations: list[Citation] | None = None,
) -> EquityResearchArtifact:
    return EquityResearchArtifact(
        artifact_id=artifact_id,
        ticker="ABC",
        candidate={},
        sources=sources or [],
        citations=citations or [],
        decision="approved",
    )


def _trade(artifact_id: str, pnl_pct: float) -> ReplayTrade:
    return ReplayTrade(
        ticker="ABC",
        sector="Technology",
        entry_day=date(2026, 1, 1),
        exit_day=date(2026, 1, 10),
        entry_price=100.0,
        exit_price=100.0 * (1 + pnl_pct),
        pnl_pct=pnl_pct,
        outcome="target" if pnl_pct > 0 else "stop",
        artifact_id=artifact_id,
    )


def test_single_citation_aggregates_into_source():
    artifact = _artifact(
        "a1",
        sources=[SourceRef(id="s1", kind="news", source="Reuters")],
        citations=[Citation(source_ref_id="s1", quote_or_summary="x", confidence=0.9)],
    )
    trade = _trade("a1", 0.05)

    result = attribute_returns_by_source([artifact], [trade])

    assert result["Reuters"].trade_count == 1
    assert result["Reuters"].expectancy_pct == 5.0
    assert result["Reuters"].win_rate == 1.0


def test_two_trades_same_source_average_together():
    artifact1 = _artifact(
        "a1",
        sources=[SourceRef(id="s1", kind="news", source="Reuters")],
        citations=[Citation(source_ref_id="s1", quote_or_summary="x", confidence=0.9)],
    )
    artifact2 = _artifact(
        "a2",
        sources=[SourceRef(id="s2", kind="news", source="Reuters")],
        citations=[Citation(source_ref_id="s2", quote_or_summary="y", confidence=0.8)],
    )
    trade1 = _trade("a1", 0.05)
    trade2 = _trade("a2", -0.05)

    result = attribute_returns_by_source([artifact1, artifact2], [trade1, trade2])

    assert result["Reuters"].trade_count == 2
    assert result["Reuters"].expectancy_pct == 0.0
    assert result["Reuters"].win_rate == 0.5


def test_artifact_with_no_citations_contributes_to_no_source():
    artifact = _artifact("a1", sources=[], citations=[])
    trade = _trade("a1", 0.05)

    result = attribute_returns_by_source([artifact], [trade])

    assert result == {}


def test_citation_with_unresolvable_source_ref_is_skipped():
    artifact = _artifact(
        "a1",
        sources=[SourceRef(id="s1", kind="news", source="Reuters")],
        citations=[Citation(source_ref_id="does-not-exist", quote_or_summary="x", confidence=0.9)],
    )
    trade = _trade("a1", 0.05)

    result = attribute_returns_by_source([artifact], [trade])

    assert result == {}


def test_duplicate_citations_to_same_source_in_one_artifact_count_trade_once():
    artifact = _artifact(
        "a1",
        sources=[
            SourceRef(id="s1", kind="news", source="Reuters"),
            SourceRef(id="s2", kind="news", source="Reuters"),
        ],
        citations=[
            Citation(source_ref_id="s1", quote_or_summary="x", confidence=0.9),
            Citation(source_ref_id="s2", quote_or_summary="y", confidence=0.8),
        ],
    )
    trade = _trade("a1", 0.05)

    result = attribute_returns_by_source([artifact], [trade])

    assert result["Reuters"].trade_count == 1
    assert result["Reuters"].expectancy_pct == 5.0
    assert result["Reuters"].win_rate == 1.0
