from __future__ import annotations

from datetime import date, timedelta

from core.assets.bar import Bar, PriceSeries
from equities.research.artifacts import EquityResearchArtifact, stable_hash
from equities.research.memory import EquityDecisionMemory, format_ticker_memory
from equities.research.store import ResearchArtifactStore


class FakeHistory:
    def __init__(self, series: dict[str, PriceSeries]) -> None:
        self._series = series

    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries:
        return self._series[ticker]


def _series(ticker: str, closes: list[float]) -> PriceSeries:
    start = date(2026, 1, 1)
    return PriceSeries(
        ticker=ticker,
        bars=[
            Bar(
                day=start + timedelta(days=idx),
                open=close,
                high=close * 1.02,
                low=close * 0.98,
                close=close,
                volume=1_000,
            )
            for idx, close in enumerate(closes)
        ],
    )


def _artifact(
    ticker: str,
    as_of: str = "2026-01-01T00:00:00+00:00",
    decision: str = "approved",
    rejection_reason: str = "",
) -> EquityResearchArtifact:
    output = None
    if decision == "approved":
        output = {
            "action": "buy",
            "entry": 100.0,
            "stop_loss": 95.0,
            "take_profit": 120.0,
            "confidence": 0.72,
            "catalyst": "FDA data readout creates an underpriced rerating window",
            "thesis": "Market underestimates pipeline value.",
        }
    elif rejection_reason:
        output = {"action": "reject", "reason": rejection_reason}
    payload = {
        "ticker": ticker,
        "as_of": as_of,
        "decision": decision,
        "rejection_reason": rejection_reason,
    }
    return EquityResearchArtifact(
        artifact_id=stable_hash(payload),
        as_of=as_of,
        ticker=ticker,
        candidate={"ticker": ticker, "evidence": "Earnings in 5d"},
        output_json=output,
        raw_output="raw model response that should not be copied into memory",
        decision=decision,  # type: ignore[arg-type]
        rejection_reason=rejection_reason,
    )


def test_memory_empty_store_has_empty_prompt_block(tmp_path):
    store = ResearchArtifactStore(tmp_path / "research_artifacts.jsonl")
    memory = EquityDecisionMemory(store, prices=None)

    ticker_memory = memory.for_ticker("ARWR")

    assert ticker_memory.prior_decisions == []
    assert ticker_memory.realized_lessons == []
    assert ticker_memory.common_rejections == []
    assert ticker_memory.recent_outcome_summary == ""
    assert format_ticker_memory(ticker_memory) == ""


def test_memory_summarizes_same_ticker_history_and_realized_outcome(tmp_path):
    store = ResearchArtifactStore(tmp_path / "research_artifacts.jsonl")
    store.append(_artifact("ARWR"))
    store.append(_artifact("MSFT"))
    prices = FakeHistory({
        "ARWR": _series("ARWR", [100.0] + [101.0] * 19 + [115.0]),
        "SPY": _series("SPY", [100.0] + [100.5] * 19 + [105.0]),
    })
    memory = EquityDecisionMemory(store, prices)

    ticker_memory = memory.for_ticker("ARWR")
    block = format_ticker_memory(ticker_memory)

    assert "approved buy confidence=0.72" in block
    assert "FDA data readout" in block
    assert "realized +15.0%" in block
    assert "alpha vs SPY +10.0%" in block
    assert "MSFT" not in block


def test_memory_tracks_rejected_decisions_and_common_patterns(tmp_path):
    store = ResearchArtifactStore(tmp_path / "research_artifacts.jsonl")
    store.append(
        _artifact(
            "ARWR",
            decision="rejected",
            rejection_reason="already priced in after 20% move",
        )
    )
    store.append(
        _artifact(
            "ARWR",
            as_of="2026-01-02T00:00:00+00:00",
            decision="rejected",
            rejection_reason="already priced in after 18% move",
        )
    )
    store.append(
        _artifact(
            "ARWR",
            as_of="2026-01-03T00:00:00+00:00",
            decision="rejected",
            rejection_reason="no clear catalyst",
        )
    )

    ticker_memory = EquityDecisionMemory(store, prices=None).for_ticker("ARWR")
    block = format_ticker_memory(ticker_memory)

    assert "rejected; already priced in after 18% move" in block
    assert "Repeated failure modes:" in block
    assert "already priced in" in block


def test_memory_format_is_compact_and_omits_raw_artifacts(tmp_path):
    store = ResearchArtifactStore(tmp_path / "research_artifacts.jsonl")
    long_reason = " ".join(["generic uncited thesis"] * 40)
    for idx in range(8):
        store.append(
            _artifact(
                "ARWR",
                as_of=f"2026-01-{idx + 1:02d}T00:00:00+00:00",
                decision="rejected",
                rejection_reason=long_reason,
            )
        )

    block = format_ticker_memory(EquityDecisionMemory(store, prices=None).for_ticker("ARWR"))

    assert len(block.splitlines()) <= 9
    assert "raw model response" not in block
    assert all(len(line) <= 190 for line in block.splitlines())
