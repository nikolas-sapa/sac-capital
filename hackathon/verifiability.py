from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "mantle-agent-decision-v1"


@dataclass(frozen=True)
class Commitment:
    """Deterministic off-chain payload plus the bytes32 hash to anchor on-chain."""

    kind: str
    source: str
    payload: dict[str, Any]
    canonical_json: str
    sha256: str

    @property
    def bytes32(self) -> str:
        return "0x" + self.sha256

    def as_record(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source": self.source,
            "schema_version": SCHEMA_VERSION,
            "hash_algorithm": "sha256",
            "bytes32": self.bytes32,
            "canonical_json": self.canonical_json,
            "payload": self.payload,
        }


def canonical_json(data: dict[str, Any]) -> str:
    """Return stable JSON for hashing and later judge verification."""

    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def commitment_for_payload(kind: str, source: str, payload: dict[str, Any]) -> Commitment:
    wrapped = {
        "kind": kind,
        "source": source,
        "schema_version": SCHEMA_VERSION,
        "payload": payload,
    }
    encoded = canonical_json(wrapped)
    return Commitment(
        kind=kind,
        source=source,
        payload=payload,
        canonical_json=encoded,
        sha256=sha256(encoded.encode("utf-8")).hexdigest(),
    )


def ledger_rows(db_path: str | Path, *, include_resolved: bool = True) -> list[dict[str, Any]]:
    """Read Polymarket paper ledger rows in the order they were created."""

    path = Path(db_path)
    if not path.exists():
        return []

    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    try:
        where = "" if include_resolved else "WHERE resolved = 0"
        rows = con.execute(f"SELECT * FROM fills {where} ORDER BY id").fetchall()
        return [dict(row) for row in rows]
    finally:
        con.close()


def ledger_commitment(row: dict[str, Any]) -> Commitment:
    """Build a judge-verifiable commitment for one agent trading decision."""

    payload = {
        "row_id": row.get("id"),
        "strategy": row.get("strategy", ""),
        "condition_id": row.get("condition_id"),
        "token_id": row.get("token_id"),
        "question": row.get("question"),
        "stake": row.get("stake"),
        "shares": row.get("shares"),
        "avg_price": row.get("avg_price"),
        "fair_prob": row.get("fair_prob"),
        "confidence": row.get("confidence"),
        "reason": row.get("reason"),
        "mode": row.get("mode"),
        "timestamp": row.get("timestamp"),
        "resolved": row.get("resolved"),
        "won": row.get("won"),
        "pnl": row.get("pnl"),
    }
    return commitment_for_payload(
        kind="polymarket_agent_decision",
        source="core.ledger.fills",
        payload=payload,
    )


def export_ledger_commitments(
    db_path: str | Path,
    *,
    include_resolved: bool = True,
) -> list[Commitment]:
    return [
        ledger_commitment(row)
        for row in ledger_rows(db_path, include_resolved=include_resolved)
    ]


def research_artifact_commitments(path: str | Path) -> list[Commitment]:
    """Hash JSONL research artifacts without requiring their Pydantic models."""

    artifact_path = Path(path)
    if not artifact_path.exists():
        return []

    commitments: list[Commitment] = []
    with artifact_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            payload["_jsonl_line"] = line_number
            commitments.append(
                commitment_for_payload(
                    kind="equity_research_artifact",
                    source=str(artifact_path),
                    payload=payload,
                )
            )
    return commitments


def records_to_jsonl(records: Iterable[dict[str, Any]]) -> str:
    return "\n".join(canonical_json(record) for record in records)

