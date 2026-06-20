"""Nightly situational-awareness digest — combines thematic concentration,
discovery-lag-by-thesis, and replay expectancy breakdowns into one text block.

Pure formatting only: no scoring/analysis logic lives here. Inputs are the
already-computed outputs of ThematicMonitor, ThesisMiner, and
DiscoveryLagCalculator (plus an already-computed ReplayReport).
"""
from __future__ import annotations

from equities.eval.replay import ReplayMetrics, ReplayReport
from equities.research.discovery_lag import DiscoveryLagCalculator
from equities.research.thesis_miner import LLMClient, ThesisMiner, ThesisResult
from equities.screen.thematic_monitor import ThematicMonitor

_DOWN_WEIGHT_THRESHOLD = 1.0


def build_digest(
    thematic_alerts: list[str],
    thesis_results: list[ThesisResult],
    discovery_lag_by_trunk: dict[str, list[tuple[str, float, float]]],
    replay_report: ReplayReport,
) -> str:
    """Pure text formatter — no I/O, safe to unit test directly."""
    lines: list[str] = [
        "🌙 NIGHTLY SITUATIONAL DIGEST",
        "─" * 32,
        "",
        "📌 Thematic concentration:",
    ]
    lines.extend(_format_thematic_section(thematic_alerts))

    lines.append("")
    lines.append("🔍 Discovery lag by thesis:")
    lines.extend(_format_thesis_section(thesis_results, discovery_lag_by_trunk))

    lines.append("")
    lines.append("📊 Replay expectancy breakdown:")
    lines.extend(_format_replay_section(replay_report))

    return "\n".join(lines)


def _format_thematic_section(thematic_alerts: list[str]) -> list[str]:
    if not thematic_alerts:
        return ["  None — no theme over concentration limit."]
    return [f"  ⚠️ {alert}" for alert in thematic_alerts]


def _format_thesis_section(
    thesis_results: list[ThesisResult],
    discovery_lag_by_trunk: dict[str, list[tuple[str, float, float]]],
) -> list[str]:
    if not thesis_results:
        return ["  None — no thesis results available."]

    lines: list[str] = []
    for result in thesis_results:
        multiplier = result.confidence_multiplier
        down_weighted = multiplier < _DOWN_WEIGHT_THRESHOLD
        flag = (
            f" (⬇ down-weighted x{multiplier:.2f} — premise partly played out)"
            if down_weighted
            else f" (confidence x{multiplier:.2f})"
        )
        lines.append(f"  • {result.trunk} — {result.thesis[:70]}{flag}")
        leaves = discovery_lag_by_trunk.get(result.trunk, [])
        if not leaves:
            lines.append("      no leaf data")
            continue
        for leaf, bottleneck_score, lag_pct in leaves:
            adjusted_lag = lag_pct * multiplier
            lines.append(
                f"      {leaf}: bottleneck={bottleneck_score:.2f} "
                f"lag={lag_pct:.1f}% adjusted_lag={adjusted_lag:.1f}%"
            )
    return lines


def _format_replay_section(replay_report: ReplayReport) -> list[str]:
    lines: list[str] = []
    for label, metrics in (("train", replay_report.train), ("validation", replay_report.validation)):
        lines.append(f"  {label}: trades={metrics.trade_count} expectancy={metrics.expectancy_pct:.2f}%")
        lines.extend(_format_breakdown("sector", metrics.sector_expectancy_pct))
        lines.extend(_format_breakdown("catalyst", metrics.catalyst_expectancy_pct))
    if not any(
        metrics.sector_expectancy_pct or metrics.catalyst_expectancy_pct
        for metrics in (replay_report.train, replay_report.validation)
    ):
        lines.append("  None — no sector/catalyst breakdown available.")
    return lines


def _format_breakdown(label: str, breakdown: dict[str, float] | None) -> list[str]:
    if not breakdown:
        return []
    parts = ", ".join(f"{name}={value:.1f}%" for name, value in breakdown.items())
    return [f"    {label}: {parts}"]


class SituationalDigestBuilder:
    """Wires the real ThematicMonitor / ThesisMiner / DiscoveryLagCalculator
    together and produces the formatted digest text. No network/LLM calls
    happen at import or construction time — only when .build() runs, and
    only through the injected dependencies.
    """

    def __init__(
        self,
        thematic_monitor: ThematicMonitor | None = None,
        thesis_miner: ThesisMiner | None = None,
        discovery_lag: DiscoveryLagCalculator | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self._thematic_monitor = thematic_monitor or ThematicMonitor()
        self._thesis_miner = thesis_miner or ThesisMiner(llm)
        self._discovery_lag = discovery_lag or DiscoveryLagCalculator()

    def build(self, open_positions: list[dict], replay_report: ReplayReport) -> str:
        thematic_alerts = self._thematic_monitor.check(open_positions)
        thesis_results = self._thesis_miner.mine_all()
        discovery_lag_by_trunk = {
            result.trunk: self._discovery_lag.score_all_leaves(result.trunk)
            for result in thesis_results
            if result.trunk
        }
        return build_digest(
            thematic_alerts=thematic_alerts,
            thesis_results=thesis_results,
            discovery_lag_by_trunk=discovery_lag_by_trunk,
            replay_report=replay_report,
        )


async def send_digest(
    builder: SituationalDigestBuilder,
    open_positions: list[dict],
    replay_report: ReplayReport,
    telegram_token: str,
    telegram_chat_id: str,
) -> None:
    """Thin async wrapper: build the text synchronously, then post it."""
    from core.alerts.telegram import TelegramAlerts

    text = builder.build(open_positions=open_positions, replay_report=replay_report)
    alerts = TelegramAlerts(telegram_token, telegram_chat_id)
    await alerts.send(text)
