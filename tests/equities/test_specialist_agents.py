from __future__ import annotations

import json
from datetime import date

from core.assets.instrument import CapTier, Instrument
from equities.analysis.agents import AnalystPacket, TradeSynthesizer, format_packets
from equities.analysis.analyst import EquityAnalyst, LLMResponse
from equities.research.store import ResearchArtifactStore
from equities.screen.event_screen import CandidateEvent, EventType


def _event(ticker: str = "ARWR") -> CandidateEvent:
    return CandidateEvent(
        instrument=Instrument(ticker, ticker, "NASDAQ", CapTier.SMALL),
        event_type=EventType.EARNINGS_APPROACHING,
        evidence="Earnings in 5d",
        urgency=0.8,
        days_to_event=5,
    )


class FakeLLM:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        self.calls.append((model, user))
        if "rankings" in user:
            content = json.dumps({
                "rankings": [{"ticker": "ARWR", "score": 8, "reason": "strong"}]
            })
        elif "Challenge this proposed swing trade" in user:
            content = json.dumps({"verdict": "pass", "objections": []})
        elif "Audit this bull/bear analysis" in user:
            content = json.dumps({"verdict": "proceed", "consistency_penalty": 0.0})
        else:
            content = json.dumps({
                "action": "buy",
                "entry": 74.0,
                "stop_loss": 68.0,
                "take_profit": 88.0,
                "confidence": 0.72,
                "horizon": "2-3 weeks",
                "catalyst": "FDA data due",
                "thesis": "Market underestimates the setup.",
                "business_quality": "Gross margins are high.",
                "valuation": "Valuation is not decisive.",
                "balance_sheet_risk": "Cash runway appears adequate.",
                "market_expectation_gap": "Coverage misses the catalyst.",
                "invalidation": "Delay breaks the thesis.",
                "evidence_citations": ["headline"],
            })
        return LLMResponse(content=content, input_tokens=100, output_tokens=50)


class FakePrices:
    def latest_close(self, ticker: str) -> float | None:
        return 74.36

    def latest_bar(self, ticker: str):
        class Bar:
            day = date.today()

        return Bar()


class FakeNews:
    def headlines(self, ticker: str, limit: int = 15) -> list[str]:
        return ["ARWR wins approval for new therapy"]


class BearishNews:
    def headlines(self, ticker: str, limit: int = 15) -> list[str]:
        return ["Analyst downgrade cites dilution risk", "Product launch delayed"]


class FakeFilings:
    def summary(self, ticker: str, days: int = 90) -> list[str]:
        return ["8-K item 2.02 filed 3d ago"]


def test_format_packets_is_compact():
    packet = AnalystPacket(
        ticker="ARWR",
        agent="technical",
        score=0.2,
        verdict="bullish",
        thesis_points=["valid price"],
        risks=[],
        citations=["price"],
    )

    assert "technical: bullish" in format_packets([packet])


def test_trade_synthesizer_rejects_multiple_bearish_packets():
    packets = [
        AnalystPacket("A", "news", -0.4, "bearish", [], ["downgrade"], []),
        AnalystPacket("A", "sentiment", -0.5, "bearish", [], ["bearish"], []),
    ]

    result = TradeSynthesizer().rejection(packets)

    assert result is not None
    assert result["action"] == "reject"
    assert result["specialist_packets"]


def test_specialist_mode_disabled_keeps_prompt_unchanged(tmp_path):
    store = ResearchArtifactStore(tmp_path / "artifacts.jsonl")
    llm = FakeLLM()
    analyst = EquityAnalyst(
        llm,
        FakePrices(),
        FakeNews(),
        FakeFilings(),
        artifact_store=store,
        specialist_agents_enabled=False,
    )

    assert analyst.analyse([_event("ARWR")])
    analyst_prompts = [
        user for _model, user in llm.calls
        if "Analyze this equity catalyst." in user
    ]
    assert "## Specialist packets" not in analyst_prompts[0]


def test_specialist_packets_are_stored_when_enabled(tmp_path):
    store = ResearchArtifactStore(tmp_path / "artifacts.jsonl")
    llm = FakeLLM()
    analyst = EquityAnalyst(
        llm,
        FakePrices(),
        FakeNews(),
        FakeFilings(),
        artifact_store=store,
        specialist_agents_enabled=True,
    )

    assert analyst.analyse([_event("ARWR")])

    analyst_artifacts = [
        artifact for artifact in store.read_all()
        if artifact.extractions[0].provider == "equity_analyst"
    ]
    assert analyst_artifacts
    assert "specialist_packets" in (analyst_artifacts[0].output_json or {})


def test_specialist_rejection_skips_deep_analyst(tmp_path):
    store = ResearchArtifactStore(tmp_path / "artifacts.jsonl")
    llm = FakeLLM()
    analyst = EquityAnalyst(
        llm,
        FakePrices(),
        BearishNews(),
        FakeFilings(),
        artifact_store=store,
        specialist_agents_enabled=True,
    )

    assert analyst.analyse([_event("ARWR")]) == []
    assert all("Analyze this equity catalyst." not in user for _model, user in llm.calls)
    assert store.read_all()[0].rejection_reason.startswith("specialist_reject")
