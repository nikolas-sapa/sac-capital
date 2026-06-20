from __future__ import annotations

from dataclasses import dataclass

from equities.eval.replay import ReplayTrade
from equities.research.artifacts import EquityResearchArtifact


@dataclass(frozen=True)
class SourceAttribution:
    trade_count: int
    expectancy_pct: float
    win_rate: float


def attribute_returns_by_source(
    artifacts: list[EquityResearchArtifact],
    trades: list[ReplayTrade],
) -> dict[str, SourceAttribution]:
    """Join trades back to the citation sources behind each artifact's thesis.

    For each trade, resolves its artifact's citations to distinct `SourceRef.source`
    names (deduping per-trade so a single trade with multiple citations to the same
    source is only counted once for that source), then aggregates `pnl_pct` per
    source: trade count, mean expectancy (%), and win rate.
    """
    artifacts_by_id = {artifact.artifact_id: artifact for artifact in artifacts}
    groups: dict[str, list[float]] = {}

    for trade in trades:
        artifact = artifacts_by_id.get(trade.artifact_id)
        if artifact is None:
            continue
        sources_by_id = {source_ref.id: source_ref.source for source_ref in artifact.sources}
        resolved_sources = {
            sources_by_id[citation.source_ref_id]
            for citation in artifact.citations
            if citation.source_ref_id in sources_by_id
        }
        for source in resolved_sources:
            groups.setdefault(source, []).append(trade.pnl_pct)

    result: dict[str, SourceAttribution] = {}
    for source, pnl_pcts in groups.items():
        wins = [pnl for pnl in pnl_pcts if pnl > 0]
        result[source] = SourceAttribution(
            trade_count=len(pnl_pcts),
            expectancy_pct=round((sum(pnl_pcts) / len(pnl_pcts)) * 100, 4),
            win_rate=round(len(wins) / len(pnl_pcts), 4),
        )
    return result
