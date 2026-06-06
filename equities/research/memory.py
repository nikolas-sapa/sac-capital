from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from core.assets.bar import PriceSeries
from equities.research.artifacts import EquityResearchArtifact


class ArtifactStore(Protocol):
    def read_all(self) -> list[EquityResearchArtifact]: ...


class HistoryProvider(Protocol):
    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries: ...


@dataclass(frozen=True)
class TickerMemory:
    ticker: str
    prior_decisions: list[str]
    realized_lessons: list[str]
    common_rejections: list[str]
    recent_outcome_summary: str


@dataclass(frozen=True)
class CrossTickerMemory:
    lessons: list[str]
    rejection_patterns: list[str]
    promoted_patterns: list[str]


class EquityDecisionMemory:
    def __init__(
        self,
        artifact_store: ArtifactStore,
        prices: HistoryProvider | None,
        benchmark_ticker: str = "SPY",
    ) -> None:
        self._artifact_store = artifact_store
        self._prices = prices
        self._benchmark_ticker = benchmark_ticker

    def for_ticker(self, ticker: str, limit: int = 5) -> TickerMemory:
        ticker = ticker.upper()
        artifacts = [
            artifact
            for artifact in self._safe_read_all()
            if artifact.ticker.upper() == ticker
        ]
        artifacts = sorted(artifacts, key=lambda artifact: artifact.as_of, reverse=True)
        recent = artifacts[: max(limit, 0)]
        decisions = [_decision_line(artifact) for artifact in recent]
        realized = [
            lesson
            for artifact in recent
            if (lesson := self._realized_lesson(artifact)) is not None
        ]
        rejections = _top_rejection_patterns(artifacts, limit=3)
        return TickerMemory(
            ticker=ticker,
            prior_decisions=decisions[:limit],
            realized_lessons=realized[:limit],
            common_rejections=rejections,
            recent_outcome_summary=_outcome_summary(realized),
        )

    def cross_ticker(self, limit: int = 10) -> CrossTickerMemory:
        artifacts = sorted(self._safe_read_all(), key=lambda artifact: artifact.as_of, reverse=True)
        recent = artifacts[: max(limit, 0)]
        rejections = _top_rejection_patterns(artifacts, limit=5)
        promoted = [
            _shorten(_thesis_or_catalyst(artifact), 130)
            for artifact in recent
            if artifact.decision == "approved" and _thesis_or_catalyst(artifact)
        ]
        lessons = [
            f"{artifact.ticker}: {_shorten(artifact.rejection_reason, 120)}"
            for artifact in recent
            if artifact.decision == "rejected" and artifact.rejection_reason
        ]
        return CrossTickerMemory(
            lessons=lessons[:limit],
            rejection_patterns=rejections,
            promoted_patterns=promoted[:limit],
        )

    def _safe_read_all(self) -> list[EquityResearchArtifact]:
        try:
            return self._artifact_store.read_all()
        except Exception:
            return []

    def _realized_lesson(self, artifact: EquityResearchArtifact) -> str | None:
        if artifact.decision != "approved" or not artifact.output_json or self._prices is None:
            return None
        try:
            entry = float(artifact.output_json["entry"])
            as_of = _parse_day(artifact.as_of)
            ticker_series = self._prices.history(artifact.ticker, period="1y").bars
            entry_idx = _first_bar_index_on_or_after(ticker_series, as_of)
            if entry_idx is None:
                return None
            exit_idx = min(len(ticker_series) - 1, entry_idx + 20)
            if exit_idx <= entry_idx:
                return None
            entry_price = min(entry, ticker_series[entry_idx].close)
            if entry_price <= 0:
                return None
            ticker_return = (ticker_series[exit_idx].close / entry_price) - 1.0
            alpha = self._benchmark_alpha(as_of, entry_idx, exit_idx, ticker_return)
        except Exception:
            return None

        parts = [f"{artifact.ticker} realized {ticker_return * 100:+.1f}% over ~20d"]
        if alpha is not None:
            parts.append(f"alpha vs {self._benchmark_ticker} {alpha * 100:+.1f}%")
        return "; ".join(parts)

    def _benchmark_alpha(
        self,
        as_of: date,
        entry_idx: int,
        exit_idx: int,
        ticker_return: float,
    ) -> float | None:
        if self._prices is None:
            return None
        try:
            bars = self._prices.history(self._benchmark_ticker, period="1y").bars
            bench_entry_idx = _first_bar_index_on_or_after(bars, as_of)
            if bench_entry_idx is None:
                return None
            bench_exit_idx = min(len(bars) - 1, bench_entry_idx + (exit_idx - entry_idx))
            entry = bars[bench_entry_idx].close
            if entry <= 0 or bench_exit_idx <= bench_entry_idx:
                return None
            benchmark_return = (bars[bench_exit_idx].close / entry) - 1.0
            return ticker_return - benchmark_return
        except Exception:
            return None


def format_ticker_memory(memory: TickerMemory, max_lines: int = 9) -> str:
    lines: list[str] = []
    if memory.prior_decisions:
        lines.append("Recent same-ticker decisions:")
        lines.extend(f"- {_shorten(item, 180)}" for item in memory.prior_decisions[:3])
    if memory.realized_lessons:
        lines.append("Realized outcomes:")
        lines.extend(f"- {_shorten(item, 180)}" for item in memory.realized_lessons[:3])
    if memory.common_rejections:
        lines.append("Repeated failure modes:")
        lines.extend(f"- {_shorten(item, 160)}" for item in memory.common_rejections[:3])
    if memory.recent_outcome_summary:
        lines.append(f"Summary: {_shorten(memory.recent_outcome_summary, 180)}")
    return "\n".join(lines[:max_lines])


def _decision_line(artifact: EquityResearchArtifact) -> str:
    day = _day_label(artifact.as_of)
    if artifact.decision == "approved":
        output = artifact.output_json or {}
        catalyst = _shorten(str(output.get("catalyst") or _thesis_or_catalyst(artifact)), 110)
        confidence = output.get("confidence")
        conf = (
            f" confidence={float(confidence):.2f}"
            if isinstance(confidence, (int, float))
            else ""
        )
        return f"{day}: approved buy{conf}; {catalyst}"
    reason = artifact.rejection_reason or (artifact.output_json or {}).get("reason", "")
    return f"{day}: {artifact.decision}; {_shorten(str(reason), 140)}"


def _top_rejection_patterns(
    artifacts: list[EquityResearchArtifact],
    limit: int,
) -> list[str]:
    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    for artifact in artifacts:
        if artifact.decision != "rejected":
            continue
        reason = artifact.rejection_reason or str((artifact.output_json or {}).get("reason", ""))
        if not reason:
            continue
        key = _normalize_reason(reason)
        counts[key] = counts.get(key, 0) + 1
        labels[key] = _shorten(reason, 130)
    ranked = sorted(counts, key=lambda key: (-counts[key], labels[key]))
    return [f"{labels[key]} ({counts[key]}x)" for key in ranked[:limit]]


def _outcome_summary(realized_lessons: list[str]) -> str:
    if not realized_lessons:
        return ""
    return f"{len(realized_lessons)} prior approved decision(s) have replayable outcome context."


def _thesis_or_catalyst(artifact: EquityResearchArtifact) -> str:
    output = artifact.output_json or {}
    return str(
        output.get("catalyst")
        or output.get("thesis")
        or artifact.candidate.get("evidence", "")
    )


def _normalize_reason(reason: str) -> str:
    return " ".join(reason.lower().replace(":", " ").split()[:8])


def _shorten(value: str, limit: int) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _day_label(value: str) -> str:
    try:
        return _parse_day(value).isoformat()
    except Exception:
        return value[:10]


def _parse_day(value: str) -> date:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return date.fromisoformat(value[:10])


def _first_bar_index_on_or_after(bars, day: date) -> int | None:
    for idx, bar in enumerate(bars):
        if bar.day >= day:
            return idx
    return None
