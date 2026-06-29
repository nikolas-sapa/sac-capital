"""Backfill research_static ledger rows into research artifact memory."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from equities.research.artifacts import static_research_decision_artifact
from equities.research.store import ResearchArtifactStore


def backfill_static_research_artifacts(
    equity_db: Path,
    artifacts_path: Path,
) -> int:
    store = ResearchArtifactStore(artifacts_path)
    existing_ids = {artifact.artifact_id for artifact in store.read_all()}

    con = sqlite3.connect(str(equity_db))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT * FROM positions "
            "WHERE strategy='research_static' AND status='closed' "
            "ORDER BY opened_at"
        ).fetchall()
    finally:
        con.close()

    added = 0
    for row in rows:
        artifact = static_research_decision_artifact(dict(row))
        if artifact.artifact_id in existing_ids:
            continue
        store.append(artifact)
        existing_ids.add(artifact.artifact_id)
        added += 1
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--equity-db", default="data/equity.db")
    parser.add_argument("--artifacts", default="data/research_artifacts.jsonl")
    args = parser.parse_args()

    added = backfill_static_research_artifacts(
        Path(args.equity_db),
        Path(args.artifacts),
    )
    print(f"backfilled_static_research_artifacts={added}")


if __name__ == "__main__":
    main()
