from datetime import datetime, timezone, timedelta

from core.markets import Market, Outcome
from core.strategy import Signal
from strategies.crypto_updown.strategy import CryptoUpDownStrategy


def _updown_market(ask_up: float = 0.45, ask_down: float = 0.45) -> Market:
    return Market(
        condition_id="cond_btc",
        question="Will BTC be higher at 3PM UTC today?",
        outcomes=[
            Outcome("up",   "Up",   ask_up   - 0.05, ask_up),
            Outcome("down", "Down", ask_down - 0.05, ask_down),
        ],
        end_date=datetime.now(tz=timezone.utc) + timedelta(hours=2),
        closed=False,
    )


def test_arb_signal_emitted_when_both_legs_cheap():
    # ask_up + ask_down + 2*fee = 0.45+0.45+0.02 = 0.92 < 1.0
    strat = CryptoUpDownStrategy(fee_per_leg=0.01)
    signals = strat.scan([_updown_market(0.45, 0.45)])
    assert len(signals) == 2  # one per leg
    token_ids = {s.token_id for s in signals}
    assert "up" in token_ids and "down" in token_ids


def test_no_signal_when_no_arb_and_repricing_disabled():
    strat = CryptoUpDownStrategy(fee_per_leg=0.01, enable_repricing=False)
    signals = strat.scan([_updown_market(0.51, 0.51)])  # sum > 1
    assert signals == []


def test_skips_closed_market():
    strat = CryptoUpDownStrategy()
    m = _updown_market()
    import dataclasses
    m2 = dataclasses.replace(m, closed=True)
    assert strat.scan([m2]) == []


def test_skips_non_updown_market():
    strat = CryptoUpDownStrategy()
    m = Market(
        condition_id="other",
        question="Will it rain in Paris tomorrow?",
        outcomes=[Outcome("yes", "Yes", 0.40, 0.45), Outcome("no", "No", 0.40, 0.45)],
        end_date=datetime.now(tz=timezone.utc) + timedelta(hours=5),
        closed=False,
    )
    assert strat.scan([m]) == []


def test_satisfies_strategy_protocol():
    from core.strategy import Strategy
    assert isinstance(CryptoUpDownStrategy(), Strategy)
