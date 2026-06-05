from datetime import date, timedelta

from core.assets.instrument import CapTier, Instrument
from equities.analysis.prompt import build_analyst_prompt, build_prefilter_prompt
from equities.screen.event_screen import CandidateEvent, EventType


def _event(ticker: str = "ARWR") -> CandidateEvent:
    return CandidateEvent(
        instrument=Instrument(ticker, ticker, "NASDAQ", CapTier.SMALL),
        event_type=EventType.EARNINGS_APPROACHING,
        evidence="Earnings in 5d",
        urgency=0.8,
        days_to_event=5,
    )


def test_prefilter_includes_all_tickers():
    events = [_event("A"), _event("B"), _event("C")]
    prompt = build_prefilter_prompt(events)
    assert "A" in prompt and "B" in prompt and "C" in prompt


def test_prefilter_includes_event_type():
    events = [_event("X")]
    prompt = build_prefilter_prompt(events)
    assert "earnings_approaching" in prompt


def test_analyst_includes_ticker_and_price():
    event = _event("ARWR")
    prompt = build_analyst_prompt(event, current_price=74.36, news=["headline1"], filings=["8-K 2.02"])
    assert "ARWR" in prompt
    assert "74.36" in prompt


def test_analyst_includes_news():
    event = _event("X")
    prompt = build_analyst_prompt(event, 50.0, news=["Big news today"], filings=[])
    assert "Big news today" in prompt


def test_analyst_includes_no_news_fallback():
    event = _event("X")
    prompt = build_analyst_prompt(event, 50.0, news=[], filings=[])
    assert "(none)" in prompt


def test_analyst_limits_news_to_8():
    event = _event("X")
    headlines = [f"headline {i}" for i in range(20)]
    prompt = build_analyst_prompt(event, 50.0, news=headlines, filings=[])
    assert "headline 7" in prompt
    assert "headline 8" not in prompt
