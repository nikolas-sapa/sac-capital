from __future__ import annotations

import sqlite3

from equities.research.store import ResearchArtifactStore
from scripts.backfill_static_research_artifacts import backfill_static_research_artifacts


def _create_positions(db_path) -> None:
    con = sqlite3.connect(str(db_path))
    con.execute(
        """
        CREATE TABLE positions (
            ticker TEXT NOT NULL,
            strategy TEXT NOT NULL,
            status TEXT NOT NULL,
            entry_price REAL NOT NULL,
            stop_loss REAL,
            take_profit REAL,
            exit_price REAL,
            exit_reason TEXT,
            realized_pnl REAL,
            confidence REAL,
            thesis TEXT NOT NULL,
            opened_at TEXT NOT NULL,
            closed_at TEXT
        )
        """
    )
    con.execute(
        "INSERT INTO positions "
        "(ticker, strategy, status, entry_price, stop_loss, take_profit, exit_price, "
        "exit_reason, realized_pnl, confidence, thesis, opened_at, closed_at) "
        "VALUES ('AMAT', 'research_static', 'closed', 100.0, NULL, NULL, 130.0, "
        "'time_stop', 3.0, 0.7, 'lagged bottleneck supplier behind AMD', "
        "'2026-01-01T00:00:00+00:00', '2026-01-20T00:00:00+00:00')"
    )
    con.commit()
    con.close()


def test_backfill_static_research_artifacts_is_idempotent(tmp_path):
    db_path = tmp_path / "equity.db"
    artifacts_path = tmp_path / "research_artifacts.jsonl"
    _create_positions(db_path)

    assert backfill_static_research_artifacts(db_path, artifacts_path) == 1
    assert backfill_static_research_artifacts(db_path, artifacts_path) == 0

    artifacts = ResearchArtifactStore(artifacts_path).read_all()
    assert len(artifacts) == 1
    artifact = artifacts[0]
    assert artifact.ticker == "AMAT"
    assert artifact.decision == "approved"
    assert artifact.prompt_version == "research_static_ledger_v1"
    assert artifact.output_json["thesis"] == "lagged bottleneck supplier behind AMD"
