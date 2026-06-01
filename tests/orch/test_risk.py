from datetime import datetime, timezone

from core.execution.base import Fill
from core.ledger import Ledger
from core.markets import Market, Outcome
from core.strategy import Signal
from orchestrator.risk import RiskGate, SizedSignal


def _market(cid: str = "m1") -> Market:
    return Market(
        condition_id=cid,
        question="Q?",
        outcomes=[Outcome("yes", "Yes", 0.4, 0.5)],
        end_date=datetime.now(tz=timezone.utc),
        closed=False,
    )


def _sig(market: Market, token: str = "yes") -> Signal:
    return Signal(
        market=market, token_id=token, fair_prob=0.6, price=0.5,
        confidence=0.7, reason="test",
    )


def _fill(market: Market, stake: float = 10.0) -> Fill:
    return Fill(
        signal=_sig(market),
        stake=stake,
        shares=stake / 0.5,
        avg_price=0.5,
        mode="paper",
        timestamp=datetime.now(tz=timezone.utc),
    )


def _sized(market: Market, stake: float, strategy: str = "llm") -> SizedSignal:
    return SizedSignal(signal=_sig(market), strategy=strategy, stake=stake)


def test_approves_within_limits(tmp_path):
    ledger = Ledger(tmp_path / "t.db")
    gate = RiskGate(ledger, max_total_exposure_pct=0.20, max_position_pct=0.02)
    ss = _sized(_market(), stake=10.0)  # 1% of 1000
    approved = gate.approve([ss], bankroll=1000.0)
    assert len(approved) == 1


def test_rejects_oversized_position(tmp_path):
    ledger = Ledger(tmp_path / "t.db")
    gate = RiskGate(ledger, max_position_pct=0.02)
    ss = _sized(_market(), stake=50.0)  # 5% of 1000 > 2%
    approved = gate.approve([ss], bankroll=1000.0)
    assert len(approved) == 0


def test_rejects_when_total_exposure_exceeded(tmp_path):
    ledger = Ledger(tmp_path / "t.db")
    # Record large open positions
    m = _market("existing")
    ledger.record(_fill(m, stake=190.0), strategy="dummy")
    # Now try to add another — total would be 190 + 15 = 205 > 200 (20% of 1000)
    gate = RiskGate(ledger, max_total_exposure_pct=0.20, max_position_pct=0.02)
    ss = _sized(_market("new"), stake=15.0)
    approved = gate.approve([ss], bankroll=1000.0)
    assert len(approved) == 0


def test_daily_loss_halt(tmp_path):
    ledger = Ledger(tmp_path / "t.db")
    m = _market("m1")
    ledger.record(_fill(m, stake=100.0), strategy="llm")
    ledger.resolve("m1", "no")  # lose the stake → pnl = -100
    gate = RiskGate(ledger, daily_loss_limit_pct=0.05)
    ss = _sized(_market("m2"), stake=5.0, strategy="llm")
    approved = gate.approve([ss], bankroll=1000.0)
    assert len(approved) == 0


def test_daily_loss_does_not_halt_other_strategy(tmp_path):
    ledger = Ledger(tmp_path / "t.db")
    m = _market("m1")
    ledger.record(_fill(m, stake=100.0), strategy="llm")
    ledger.resolve("m1", "no")
    gate = RiskGate(ledger, daily_loss_limit_pct=0.05)
    ss = _sized(_market("m2"), stake=5.0, strategy="weather")  # different strategy
    approved = gate.approve([ss], bankroll=1000.0)
    assert len(approved) == 1
