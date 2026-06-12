"""Alpaca order/position reconciliation for the equity paper ledger."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import Settings
from equities.execution.alpaca import AlpacaOrder, AlpacaPaperExecutor
from equities.ledger_equity import EquityLedger

_UNFILLED_TERMINAL = {"canceled", "expired", "rejected"}
_SUBMITTED = {"accepted", "new", "pending_new", "pending_replace"}


@dataclass
class ReconcileResult:
    orders_checked: int = 0
    orders_updated: int = 0
    positions_voided: int = 0
    broker_positions: int = 0
    mismatches: list[str] = field(default_factory=list)


def reconcile_alpaca(
    settings: Settings,
    *,
    executor: AlpacaPaperExecutor | None = None,
    ledger: EquityLedger | None = None,
    log_path: str | Path = "data/alpaca_reconcile.log",
) -> ReconcileResult:
    """Sync Alpaca paper order status into the local equity ledger."""
    owns_ledger = ledger is None
    ledger = ledger or EquityLedger(settings.equity_ledger_path)
    executor = executor or AlpacaPaperExecutor(settings)
    result = ReconcileResult()

    try:
        open_positions = ledger.open_positions()
        broker_positions = {pos.symbol: pos for pos in executor.list_positions()}
        result.broker_positions = len(broker_positions)
        local_filled_by_ticker: dict[str, float] = {}

        for pos in open_positions:
            if pos.get("execution_provider") != "alpaca_paper":
                continue
            order_id = pos.get("broker_order_id") or ""
            if not order_id:
                result.mismatches.append(f"{pos['ticker']}: missing_broker_order_id")
                continue

            order = executor.get_order(order_id)
            result.orders_checked += 1
            _update_ledger_order(ledger, pos["id"], order)
            result.orders_updated += 1

            if order.status in _UNFILLED_TERMINAL and order.filled_qty <= 0:
                ledger.void_position(
                    pos["id"],
                    reason=f"broker_{order.status}_unfilled",
                    closed_at=datetime.now(tz=timezone.utc),
                    status=order.status,
                )
                result.positions_voided += 1
                continue

            if order.filled_qty > 0:
                ticker = str(pos["ticker"])
                local_filled_by_ticker[ticker] = (
                    local_filled_by_ticker.get(ticker, 0.0) + float(order.filled_qty)
                )

        _append_position_mismatches(result, local_filled_by_ticker, broker_positions)

        _write_reconcile_log(log_path, result)
        print(
            "Alpaca reconcile: "
            f"orders_checked={result.orders_checked} "
            f"orders_updated={result.orders_updated} "
            f"positions_voided={result.positions_voided} "
            f"mismatches={len(result.mismatches)}"
        )
        for mismatch in result.mismatches:
            print(f"  MISMATCH {mismatch}")
        return result
    finally:
        if owns_ledger:
            ledger.close()


def _append_position_mismatches(
    result: ReconcileResult,
    local_filled_by_ticker: dict[str, float],
    broker_positions: dict[str, Any],
) -> None:
    """Compare aggregate local filled lots with Alpaca's aggregate positions."""
    for ticker, local_qty in sorted(local_filled_by_ticker.items()):
        broker_pos = broker_positions.get(ticker)
        if broker_pos is None:
            result.mismatches.append(f"{ticker}: filled_order_missing_broker_position")
            continue
        if abs(broker_pos.qty - local_qty) > 1e-6:
            result.mismatches.append(
                f"{ticker}: qty_mismatch local={local_qty:.6f} broker={broker_pos.qty:.6f}"
            )


def _update_ledger_order(ledger: EquityLedger, position_id: int, order: AlpacaOrder) -> None:
    local_status = _local_status(order)
    avg_fill = order.filled_avg_price if order.filled_avg_price is not None else None
    has_fill = order.filled_qty > 0 and avg_fill is not None
    ledger.update_broker_order(
        position_id,
        broker_order_status=order.status,
        broker_filled_qty=order.filled_qty,
        broker_avg_fill_price=order.filled_avg_price,
        status=local_status,
        entry_price=avg_fill if has_fill else None,
        shares=order.filled_qty if order.filled_qty > 0 else None,
        broker_submitted_at=order.submitted_at,
        broker_filled_at=order.filled_at,
        broker_canceled_at=order.canceled_at or order.expired_at,
        broker_raw_json=json.dumps(order.raw or {}, sort_keys=True),
    )


def _local_status(order: AlpacaOrder) -> str:
    if order.status == "filled":
        return "open"
    if order.status == "partially_filled":
        return "partially_filled"
    if order.status in _SUBMITTED:
        return "submitted"
    if order.status in _UNFILLED_TERMINAL:
        return order.status
    return "submitted"


def _write_reconcile_log(path: str | Path, result: ReconcileResult) -> None:
    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = asdict(result)
    payload["ts"] = datetime.now(tz=timezone.utc).isoformat()
    with log_path.open("a") as f:
        f.write(json.dumps(payload, sort_keys=True) + "\n")
