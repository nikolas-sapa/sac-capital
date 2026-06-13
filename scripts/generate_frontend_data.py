"""
generate_frontend_data.py

Reads existing data files and writes two JSON artifacts to frontend/public/:
  - mantle_commitments.sample.json  (all JSONL records as a JSON array)
  - performance_summary.json        (computed equity + commitment stats)

Usage:
    python scripts/generate_frontend_data.py
    python scripts/generate_frontend_data.py --ledger data/mantle_commitments.jsonl \
        --equity-csv data/equity.csv --out-dir frontend/public
"""

import argparse
import csv
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args():
    p = argparse.ArgumentParser(description="Generate frontend JSON data files.")
    p.add_argument(
        "--ledger",
        default="data/mantle_commitments.jsonl",
        help="Path to JSONL commitments ledger (relative to repo root)",
    )
    p.add_argument(
        "--equity-csv",
        default="data/equity.csv",
        help="Path to equity trades CSV (relative to repo root)",
    )
    p.add_argument(
        "--equity-db",
        default="data/equity.db",
        help="Path to equity SQLite DB (relative to repo root)",
    )
    p.add_argument(
        "--out-dir",
        default="frontend/public",
        help="Output directory for JSON artifacts (relative to repo root)",
    )
    return p.parse_args()


def _commitment_canonical_json(record: dict) -> str:
    wrapped = {
        "kind": record["kind"],
        "payload": record["payload"],
        "schema_version": record["schema_version"],
        "source": record["source"],
    }
    return json.dumps(wrapped, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def read_commitments(ledger_path: Path) -> list:
    records = []
    with ledger_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rec = json.loads(line)
                if "canonical_json" not in rec:
                    rec["canonical_json"] = _commitment_canonical_json(rec)
                records.append(rec)
    return records


def compute_equity_stats(csv_path: Path) -> dict:
    total = 0
    closed = 0
    open_active = 0
    realized_pnl_sum = 0.0
    winning_closed = 0
    confidence_values = []
    strategy_counts = defaultdict(int)

    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            total += 1
            status = row.get("status", "").strip().lower()

            if status == "closed":
                closed += 1
                rpnl_raw = row.get("realized_pnl", "").strip()
                if rpnl_raw:
                    try:
                        rpnl = float(rpnl_raw)
                        realized_pnl_sum += rpnl
                        if rpnl > 0:
                            winning_closed += 1
                    except ValueError:
                        pass
            elif status in ("open", "active"):
                open_active += 1

            conf_raw = row.get("confidence", "").strip()
            if conf_raw:
                try:
                    confidence_values.append(float(conf_raw))
                except ValueError:
                    pass

            strategy = row.get("strategy", "").strip()
            if strategy:
                strategy_counts[strategy] += 1

    win_rate = (winning_closed / closed) if closed > 0 else 0.0
    avg_confidence = (
        sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
    )

    strategies = sorted(
        [{"name": k, "count": v} for k, v in strategy_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )

    return {
        "total": total,
        "closed": closed,
        "open": open_active,
        "realized_pnl": round(realized_pnl_sum, 6),
        "win_rate": round(win_rate, 6),
        "avg_confidence": round(avg_confidence, 6),
    }, strategies


def export_equity_positions(db_path: Path) -> list[dict]:
    """Read positions from SQLite and return as frontend-compatible dicts."""
    if not db_path.exists():
        return []
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM positions ORDER BY id").fetchall()
    con.close()
    positions = []
    for r in rows:
        d = dict(r)
        analysis_raw = d.get("analysis_json", "{}")
        try:
            analysis = json.loads(analysis_raw) if analysis_raw else {}
        except (json.JSONDecodeError, TypeError):
            analysis = {}
        pos = {
            "id": str(d.get("id", "")),
            "ticker": d.get("ticker", ""),
            "side": d.get("side", "buy"),
            "status": d.get("status", "open"),
            "shares": d.get("shares"),
            "entry_price": d.get("entry_price"),
            "mark_price": d.get("mark_price"),
            "stop_loss": d.get("stop_loss"),
            "take_profit": d.get("take_profit"),
            "unrealized_pnl": d.get("unrealized_pnl"),
            "realized_pnl": d.get("realized_pnl"),
            "exit_price": d.get("exit_price"),
            "exit_reason": d.get("exit_reason"),
            "confidence": d.get("confidence"),
            "strategy": d.get("strategy", ""),
            "mode": d.get("mode", "paper"),
            "opened_at": d.get("opened_at", ""),
            "closed_at": d.get("closed_at"),
            "analysis": analysis if analysis else None,
        }
        positions.append(pos)
    return positions


def main():
    args = parse_args()

    ledger_path = REPO_ROOT / args.ledger
    equity_path = REPO_ROOT / args.equity_csv
    equity_db_path = REPO_ROOT / args.equity_db
    out_dir = REPO_ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Output A: mantle_commitments.sample.json ---
    commitments = read_commitments(ledger_path)
    commitments_out = out_dir / "mantle_commitments.sample.json"
    commitments_out.write_text(
        json.dumps(commitments, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    commitments_size = commitments_out.stat().st_size

    # --- Output B: performance_summary.json ---
    equity_stats, strategies = compute_equity_stats(equity_path)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_commitments": len(commitments),
        "equity_trades": equity_stats,
        "strategies": strategies,
    }
    summary_out = out_dir / "performance_summary.json"
    summary_out.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    summary_size = summary_out.stat().st_size

    # --- Output C: equity_positions.json (from SQLite with full analysis) ---
    positions = export_equity_positions(equity_db_path)
    if positions:
        positions_out = out_dir / "equity_positions.json"
        positions_out.write_text(
            json.dumps(positions, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Wrote {positions_out.relative_to(REPO_ROOT)}  ({positions_out.stat().st_size:,} bytes, {len(positions)} positions)")
    else:
        print("Skipped equity_positions.json — no DB or empty")

    print(f"Wrote {commitments_out.relative_to(REPO_ROOT)}  ({commitments_size:,} bytes, {len(commitments)} records)")
    print(f"Wrote {summary_out.relative_to(REPO_ROOT)}  ({summary_size:,} bytes)")
    print(f"  total_commitments : {summary['total_commitments']}")
    print(f"  equity_trades     : {equity_stats}")
    print(f"  strategies        : {strategies}")


if __name__ == "__main__":
    main()
