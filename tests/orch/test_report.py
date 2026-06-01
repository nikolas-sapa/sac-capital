from datetime import datetime, timezone

from core.execution.base import Fill
from core.ledger import Ledger
from core.markets import Market, Outcome
from core.strategy import Signal
from orchestrator.report import daily_report


def _market(cid: str = "m1") -> Market:
    return Market(
        condition_id=cid,
        question="Q?",
        outcomes=[Outcome("yes", "Yes", 0.4, 0.5)],
        end_date=datetime.now(tz=timezone.utc),
        closed=False,
    )


def _fill(market: Market, stake: float = 10.0) -> Fill:
    sig = Signal(
        market=market, token_id="yes", fair_prob=0.6, price=0.5,
        confidence=0.7, reason="test",
    )
    return Fill(
        signal=sig, stake=stake, shares=stake / 0.5,
        avg_price=0.5, mode="paper",
        timestamp=datetime.now(tz=timezone.utc),
    )


def test_empty_ledger_produces_report(tmp_path):
    ledger = Ledger(tmp_path / "t.db")
    report = daily_report(ledger)
    assert "PORTFOLIO" in report
    assert "total_pnl" in report


def test_report_includes_strategy_name(tmp_path):
    ledger = Ledger(tmp_path / "t.db")
    m = _market("m1")
    ledger.record(_fill(m), strategy="llm")
    ledger.resolve("m1", "yes")
    report = daily_report(ledger)
    assert "llm" in report
    assert "win_rate" in report


def test_report_shows_open_positions(tmp_path):
    ledger = Ledger(tmp_path / "t.db")
    m = _market("m1")
    ledger.record(_fill(m, stake=25.0), strategy="weather")
    # Not resolved — should appear in open positions
    report = daily_report(ledger)
    assert "open_exposure" in report
