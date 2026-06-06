"""Alpaca paper execution adapter for equity orders."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import httpx

from core.config import Settings
from equities.strategy import Recommendation


@dataclass(frozen=True)
class AlpacaOrder:
    id: str
    client_order_id: str
    symbol: str
    side: str
    qty: float
    status: str
    type: str
    time_in_force: str
    filled_qty: float = 0.0
    filled_avg_price: float | None = None
    submitted_at: str = ""
    filled_at: str = ""
    canceled_at: str = ""
    expired_at: str = ""
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class AlpacaAccount:
    id: str
    status: str
    currency: str
    buying_power: float
    portfolio_value: float
    trading_blocked: bool
    account_blocked: bool
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class AlpacaPosition:
    asset_id: str
    symbol: str
    qty: float
    side: str
    market_value: float
    avg_entry_price: float
    current_price: float | None = None
    unrealized_pl: float | None = None
    raw: dict[str, Any] | None = None


class AlpacaPaperExecutor:
    """Submit paper-only equity orders to Alpaca after local risk approval."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.alpaca_paper:
            raise ValueError("AlpacaPaperExecutor requires ALPACA_PAPER=true")
        if not settings.alpaca_api_key_id or not settings.alpaca_secret_key:
            raise ValueError("Missing Alpaca API credentials")
        if "paper-api.alpaca.markets" not in settings.alpaca_base_url:
            raise ValueError("Refusing to use non-paper Alpaca base URL")

        self._base_url = settings.alpaca_base_url.rstrip("/")
        if self._base_url.endswith("/v2"):
            self._base_url = self._base_url[:-3]
        self._headers = {
            "APCA-API-KEY-ID": settings.alpaca_api_key_id,
            "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
            "Content-Type": "application/json",
        }
        self._client = client or httpx.Client(timeout=30.0)

    def buy(
        self,
        recommendation: Recommendation,
        shares: float,
        *,
        client_order_id: str | None = None,
        max_notional: float | None = None,
    ) -> AlpacaOrder:
        notional = shares * recommendation.entry
        if max_notional is not None and notional > max_notional:
            raise ValueError(
                f"Alpaca order notional ${notional:.2f} exceeds max_notional ${max_notional:.2f}"
            )
        account = self.get_account()
        if account.trading_blocked or account.account_blocked:
            raise RuntimeError("Alpaca account is blocked from trading")
        if account.buying_power < notional:
            raise RuntimeError(
                f"Alpaca buying power ${account.buying_power:.2f} below order notional ${notional:.2f}"
            )
        return self._submit_order(
            symbol=recommendation.instrument.ticker,
            qty=shares,
            side="buy",
            order_type="limit",
            limit_price=recommendation.entry,
            client_order_id=client_order_id or client_order_id_for(recommendation, shares),
        )

    def sell(self, ticker: str, shares: float) -> AlpacaOrder:
        return self._submit_order(symbol=ticker, qty=shares, side="sell", order_type="market")

    def get_account(self) -> AlpacaAccount:
        resp = self._client.get(
            f"{self._base_url}/v2/account",
            headers=self._headers,
        )
        return _json_or_raise(resp, "Alpaca get account failed", _account_from_json)

    def get_order(self, order_id: str) -> AlpacaOrder:
        if not order_id:
            raise ValueError("Alpaca order id is required")
        resp = self._client.get(
            f"{self._base_url}/v2/orders/{order_id}",
            headers=self._headers,
        )
        return _json_or_raise(resp, "Alpaca get order failed", _order_from_json)

    def list_orders(self, status: str = "all", limit: int = 50) -> list[AlpacaOrder]:
        if limit <= 0:
            raise ValueError("Alpaca list orders limit must be positive")
        resp = self._client.get(
            f"{self._base_url}/v2/orders",
            headers=self._headers,
            params={"status": status, "limit": limit},
        )
        return _json_or_raise(
            resp,
            "Alpaca list orders failed",
            lambda data: [_order_from_json(order) for order in data],
        )

    def list_positions(self) -> list[AlpacaPosition]:
        resp = self._client.get(
            f"{self._base_url}/v2/positions",
            headers=self._headers,
        )
        return _json_or_raise(
            resp,
            "Alpaca list positions failed",
            lambda data: [_position_from_json(position) for position in data],
        )

    def cancel_order(self, order_id: str) -> None:
        if not order_id:
            raise ValueError("Alpaca order id is required")
        resp = self._client.delete(
            f"{self._base_url}/v2/orders/{order_id}",
            headers=self._headers,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Alpaca cancel order failed ({resp.status_code}): {resp.text}")

    def _submit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str,
        *,
        limit_price: float | None = None,
        client_order_id: str | None = None,
    ) -> AlpacaOrder:
        if qty <= 0:
            raise ValueError("Alpaca order quantity must be positive")
        if order_type == "limit" and (limit_price is None or limit_price <= 0):
            raise ValueError("Alpaca limit orders require a positive limit_price")

        payload = {
            "symbol": symbol,
            "qty": _format_qty(qty),
            "side": side,
            "type": order_type,
            "time_in_force": "day",
        }
        if limit_price is not None:
            payload["limit_price"] = _format_price(limit_price)
        if client_order_id:
            payload["client_order_id"] = client_order_id
        resp = self._client.post(
            f"{self._base_url}/v2/orders",
            headers=self._headers,
            json=payload,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Alpaca order rejected ({resp.status_code}): {resp.text}")
        return _order_from_json(resp.json())


def client_order_id_for(recommendation: Recommendation, shares: float) -> str:
    """Stable idempotency key for the same ticker/signal/size."""
    payload = "|".join([
        "equity",
        recommendation.side,
        recommendation.instrument.ticker,
        f"{recommendation.entry:.4f}",
        f"{recommendation.stop_loss or 0.0:.4f}",
        f"{recommendation.take_profit or 0.0:.4f}",
        f"{shares:.6f}",
        recommendation.sleeve.value,
        recommendation.catalyst,
    ])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:18]
    return f"eq-{recommendation.side}-{recommendation.instrument.ticker}-{digest}"[:48]


def _format_qty(qty: float) -> str:
    return f"{qty:.6f}".rstrip("0").rstrip(".")


def _format_price(price: float) -> str:
    return f"{price:.2f}"


def _json_or_raise(resp: httpx.Response, message: str, parser):
    if resp.status_code >= 400:
        raise RuntimeError(f"{message} ({resp.status_code}): {resp.text}")
    return parser(resp.json())


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _order_from_json(data: dict[str, Any]) -> AlpacaOrder:
    return AlpacaOrder(
        id=str(data.get("id", "")),
        client_order_id=str(data.get("client_order_id", "")),
        symbol=str(data.get("symbol", "")),
        side=str(data.get("side", "")),
        qty=float(data.get("qty") or 0.0),
        status=str(data.get("status", "")),
        type=str(data.get("type", "")),
        time_in_force=str(data.get("time_in_force", "")),
        filled_qty=float(data.get("filled_qty") or 0.0),
        filled_avg_price=_float_or_none(data.get("filled_avg_price")),
        submitted_at=str(data.get("submitted_at") or ""),
        filled_at=str(data.get("filled_at") or ""),
        canceled_at=str(data.get("canceled_at") or ""),
        expired_at=str(data.get("expired_at") or ""),
        raw=data,
    )


def _account_from_json(data: dict[str, Any]) -> AlpacaAccount:
    return AlpacaAccount(
        id=str(data.get("id", "")),
        status=str(data.get("status", "")),
        currency=str(data.get("currency", "")),
        buying_power=float(data.get("buying_power") or 0.0),
        portfolio_value=float(data.get("portfolio_value") or 0.0),
        trading_blocked=bool(data.get("trading_blocked", False)),
        account_blocked=bool(data.get("account_blocked", False)),
        raw=data,
    )


def _position_from_json(data: dict[str, Any]) -> AlpacaPosition:
    return AlpacaPosition(
        asset_id=str(data.get("asset_id", "")),
        symbol=str(data.get("symbol", "")),
        qty=float(data.get("qty") or 0.0),
        side=str(data.get("side", "")),
        market_value=float(data.get("market_value") or 0.0),
        avg_entry_price=float(data.get("avg_entry_price") or 0.0),
        current_price=_float_or_none(data.get("current_price")),
        unrealized_pl=_float_or_none(data.get("unrealized_pl")),
        raw=data,
    )
