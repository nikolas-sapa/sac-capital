"""Tests for the nightly consolidation job."""
from datetime import date, datetime, timezone

import pytest

from core.execution.base import Fill
from core.ledger import Ledger
from core.markets import Market, Outcome
from core.strategy import Signal
from harness.nightly import run_nightly
from harness.obsidian import ObsidianVault
from harness.params import ParamStore


def _market(cid: str = "m1") -> Market:
    return Market(
        condition_id=cid,
        question="Q?",
        outcomes=[
            Outcome("yes", "Yes", 0.4, 0.5),
            Outcome("no", "No", 0.4, 0.5),
        ],
        end_date=datetime.now(tz=timezone.utc),
        closed=False,
    )


def _fill(market: Market, stake: float = 10.0) -> Fill:
    sig = Signal(
        market=market, token_id="yes", fair_prob=0.6, price=0.5,
        confidence=0.7, reason="t",
    )
    return Fill(
        signal=sig, stake=stake, shares=stake / 0.5,
        avg_price=0.5, mode="paper",
        timestamp=datetime.now(tz=timezone.utc),
    )


class AutoLearner:
    """Stub learner that always proposes an auto change."""

    def run(self, stats, store, vault):
        return {
            "strategy": "llm",
            "key": "min_edge",
            "value": 0.09,
            "reason": "test auto",
            "evidence": "stub",
            "type": "auto",
        }


class ApprovalLearner:
    """Stub learner that always proposes an approval change."""

    def run(self, stats, store, vault):
        return {
            "strategy": "llm",
            "key": "min_conf",
            "value": 0.65,
            "reason": "big jump",
            "evidence": "stub",
            "type": "approval",
        }


class NullLearner:
    """Stub learner that has nothing to propose."""

    def run(self, stats, store, vault):
        return None


def test_nightly_writes_daily_log(tmp_path):
    ledger = Ledger(tmp_path / "l.db")
    vault = ObsidianVault(tmp_path / "vault")
    store = ParamStore(tmp_path / "p.db")

    run_nightly(ledger, store, vault, [NullLearner()])

    today = date.today().isoformat()
    log = tmp_path / "vault" / "daily" / f"{today}.md"
    assert log.exists()
    assert "Nightly Consolidation" in log.read_text()


def test_nightly_updates_index(tmp_path):
    ledger = Ledger(tmp_path / "l.db")
    vault = ObsidianVault(tmp_path / "vault")
    store = ParamStore(tmp_path / "p.db")

    run_nightly(ledger, store, vault, [])
    index = tmp_path / "vault" / "index.md"
    assert index.exists()


def test_auto_learner_applies_param(tmp_path):
    ledger = Ledger(tmp_path / "l.db")
    vault = ObsidianVault(tmp_path / "vault")
    store = ParamStore(tmp_path / "p.db")

    result = run_nightly(ledger, store, vault, [AutoLearner()])
    assert len(result["auto_applied"]) == 1
    assert store.get("llm", "min_edge") == pytest.approx(0.09)


def test_approval_learner_queues_proposal(tmp_path):
    ledger = Ledger(tmp_path / "l.db")
    vault = ObsidianVault(tmp_path / "vault")
    store = ParamStore(tmp_path / "p.db")

    result = run_nightly(ledger, store, vault, [ApprovalLearner()])
    assert len(result["approval_queued"]) == 1
    # Param not yet applied (needs human approval)
    assert store.get("llm", "min_conf") is None


def test_auto_change_written_to_changelog(tmp_path):
    ledger = Ledger(tmp_path / "l.db")
    vault = ObsidianVault(tmp_path / "vault")
    store = ParamStore(tmp_path / "p.db")

    run_nightly(ledger, store, vault, [AutoLearner()])
    changelog = tmp_path / "vault" / "params" / "CHANGELOG.md"
    assert changelog.exists()
    assert "min_edge" in changelog.read_text()


def test_nightly_includes_strategy_stats_in_log(tmp_path):
    ledger = Ledger(tmp_path / "l.db")
    m = _market("m1")
    ledger.record(_fill(m), strategy="weather")
    ledger.resolve("m1", "yes")

    vault = ObsidianVault(tmp_path / "vault")
    store = ParamStore(tmp_path / "p.db")
    run_nightly(ledger, store, vault, [])

    today = date.today().isoformat()
    log = (tmp_path / "vault" / "daily" / f"{today}.md").read_text()
    assert "weather" in log
