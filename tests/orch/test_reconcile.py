from datetime import datetime, timezone, timedelta

from core.markets import Market, Outcome
from core.strategy import Signal
from orchestrator.reconcile import reconcile


def _market(cid: str = "m1") -> Market:
    return Market(
        condition_id=cid,
        question="Q?",
        outcomes=[
            Outcome("yes", "Yes", 0.4, 0.5),
            Outcome("no", "No", 0.4, 0.5),
        ],
        end_date=datetime.now(tz=timezone.utc) + timedelta(hours=2),
        closed=False,
    )


def _sig(
    market: Market,
    token: str,
    confidence: float = 0.7,
    reason: str = "test",
) -> Signal:
    return Signal(
        market=market,
        token_id=token,
        fair_prob=0.6,
        price=0.5,
        confidence=confidence,
        reason=reason,
    )


def test_empty_input():
    assert reconcile([]) == []


def test_single_signal_passes_through():
    m = _market()
    sig = _sig(m, "yes")
    assert reconcile([sig]) == [sig]


def test_duplicate_same_token_keeps_higher_confidence():
    m = _market()
    low = _sig(m, "yes", confidence=0.5)
    high = _sig(m, "yes", confidence=0.9)
    result = reconcile([low, high])
    assert len(result) == 1
    assert result[0].confidence == 0.9


def test_opposing_non_arb_signals_dropped():
    m = _market()
    buy_yes = _sig(m, "yes", reason="weather")
    buy_no = _sig(m, "no", reason="llm")
    result = reconcile([buy_yes, buy_no])
    assert result == []


def test_arb_set_kept():
    m = _market()
    arb_yes = _sig(m, "yes", reason="arb: profit/unit=0.08 fee=0.01")
    arb_no = _sig(m, "no", reason="arb: profit/unit=0.08 fee=0.01")
    result = reconcile([arb_yes, arb_no])
    assert len(result) == 2
    tokens = {s.token_id for s in result}
    assert "yes" in tokens and "no" in tokens


def test_different_markets_all_kept():
    m1, m2 = _market("m1"), _market("m2")
    s1 = _sig(m1, "yes")
    s2 = _sig(m2, "yes")
    result = reconcile([s1, s2])
    assert len(result) == 2


def test_mixed_arb_and_non_arb_on_same_market_drops_all():
    m = _market()
    arb_yes = _sig(m, "yes", reason="arb: profit=0.08")
    non_arb_no = _sig(m, "no", reason="llm model")
    result = reconcile([arb_yes, non_arb_no])
    assert result == []
