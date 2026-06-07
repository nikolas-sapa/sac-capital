from __future__ import annotations

from datetime import datetime, timezone

from core.execution.base import Fill
from core.ledger import Ledger
from core.markets import Market, Outcome
from core.strategy import Signal
from hackathon.verifiability import (
    canonical_json,
    export_ledger_commitments,
    records_to_jsonl,
)


def _fill() -> Fill:
    market = Market(
        condition_id="cond-1",
        question="Will Mantle AI agents win?",
        outcomes=[
            Outcome(token_id="yes", label="Yes", best_bid=0.5, best_ask=0.52),
            Outcome(token_id="no", label="No", best_bid=0.47, best_ask=0.49),
        ],
        end_date=datetime(2026, 7, 3, tzinfo=timezone.utc),
        closed=False,
    )
    signal = Signal(
        market=market,
        token_id="yes",
        fair_prob=0.64,
        price=0.52,
        confidence=0.8,
        reason="LLM found positive edge after evidence review",
    )
    return Fill(
        signal=signal,
        stake=10.0,
        shares=19.0,
        avg_price=0.526,
        timestamp=datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc),
        mode="paper",
    )


def test_canonical_json_is_stable() -> None:
    assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'


def test_export_ledger_commitments_are_deterministic(tmp_path) -> None:
    ledger = Ledger(tmp_path / "ledger.db")
    ledger.record(_fill(), strategy="llm_probability")
    ledger.close()

    first = export_ledger_commitments(tmp_path / "ledger.db")[0]
    second = export_ledger_commitments(tmp_path / "ledger.db")[0]

    assert first.sha256 == second.sha256
    assert first.bytes32.startswith("0x")
    assert len(first.bytes32) == 66
    assert first.payload["strategy"] == "llm_probability"
    assert first.payload["condition_id"] == "cond-1"


def test_records_to_jsonl_outputs_one_canonical_line_per_record() -> None:
    text = records_to_jsonl([{"b": 2, "a": 1}, {"d": 4, "c": 3}])
    assert text.splitlines() == ['{"a":1,"b":2}', '{"c":3,"d":4}']

