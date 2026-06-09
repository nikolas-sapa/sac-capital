"""Mantle on-chain signals — mETH staking APY + Mantle network gas price.

Used as a Mantle-native macro regime context layer for the equity analyst.
Both fetches are independent; partial results are valid.
Never raises — all errors surface in MantleSignal.error.

Signal sources
--------------
mETH APY  : DeFiLlama Yields API (primary — no auth, stable public endpoint)
            pool id: b9f2f00a-ba96-4589-a171-dde979a23d87 (meth-protocol/METH)
            Fallback: meth.mantle.xyz direct API endpoints (tried if DeFiLlama fails)
Gas price : Mantle mainnet RPC via eth_gasPrice JSON-RPC call
            https://rpc.mantle.xyz
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# DeFiLlama chart endpoint — returns time-series, last entry is current APY
_DEFILLAMA_CHART_URL = (
    "https://yields.llama.fi/chart/b9f2f00a-ba96-4589-a171-dde979a23d87"
)

# mETH protocol direct API — fallback if DeFiLlama is unavailable
_METH_FALLBACK_ENDPOINTS = [
    "https://meth.mantle.xyz/api/v1/staking-info",
    "https://meth.mantle.xyz/api/v1/apr",
    "https://api.mantle.xyz/meth/staking-info",
]

_MANTLE_RPC = "https://rpc.mantle.xyz"


@dataclass
class MantleSignal:
    meth_apy: float | None        # e.g. 0.042 = 4.2 % (ratio, not percentage)
    gas_price_gwei: float | None  # e.g. 50.0 Gwei — network congestion proxy
    fetched_at: str               # ISO-8601 UTC timestamp
    source: str                   # always set; describes which APIs responded
    error: str | None             # concatenated error messages, or None on full success


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_json(url: str, *, timeout: float, body: bytes | None = None,
                method: str = "GET") -> dict:
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _extract_apy_from_direct(payload: dict) -> float | None:
    """Try several known field paths used by mETH direct API variants."""
    candidates = [
        payload.get("apr"),
        payload.get("apy"),
        payload.get("stakingApr"),
        payload.get("stakingApy"),
        payload.get("currentApr"),
        payload.get("currentApy"),
    ]
    if isinstance(payload.get("data"), dict):
        d = payload["data"]
        candidates += [
            d.get("apr"),
            d.get("apy"),
            d.get("stakingApr"),
            d.get("stakingApy"),
            d.get("currentApr"),
            d.get("currentApy"),
        ]
    for val in candidates:
        if val is not None:
            try:
                f = float(val)
                # Normalise: values > 1.0 are percentage points (e.g. 4.2 → 0.042)
                return f / 100.0 if f > 1.0 else f
            except (TypeError, ValueError):
                continue
    return None


def _fetch_meth_apy_defillama(timeout: float) -> tuple[float | None, str | None]:
    """Primary: DeFiLlama chart endpoint — last entry is current APY. Returns (apy_ratio, error_msg)."""
    try:
        payload = _fetch_json(_DEFILLAMA_CHART_URL, timeout=timeout)
        # Returns {"status":"ok","data":[{...}, ..., {"timestamp":..., "apy": 1.758, ...}]}
        data_list = payload.get("data")
        if not data_list:
            return None, f"DeFiLlama: empty data list in response"
        last = data_list[-1]
        apy_raw = last.get("apy") or last.get("apyBase")
        if apy_raw is not None:
            f = float(apy_raw)
            # DeFiLlama always returns percentage points (e.g. 1.758 = 1.758%)
            return f / 100.0, None
        return None, f"DeFiLlama: unrecognised entry shape {list(last.keys())}"
    except urllib.error.HTTPError as exc:
        return None, f"DeFiLlama: HTTP {exc.code}"
    except Exception as exc:
        return None, f"DeFiLlama: {exc}"


def _fetch_meth_apy_direct(timeout: float) -> tuple[float | None, str | None]:
    """Fallback: try mETH direct API endpoints. Returns (apy_ratio, error_msg)."""
    errors: list[str] = []
    for url in _METH_FALLBACK_ENDPOINTS:
        try:
            payload = _fetch_json(url, timeout=timeout)
            apy = _extract_apy_from_direct(payload)
            if apy is not None:
                return apy, None
            errors.append(f"{url}: unrecognised shape {list(payload.keys())}")
        except urllib.error.HTTPError as exc:
            errors.append(f"{url}: HTTP {exc.code}")
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    return None, "; ".join(errors)


def _fetch_meth_apy(timeout: float) -> tuple[float | None, str | None]:
    """Try DeFiLlama first, fall back to direct mETH API. Returns (apy, error_msg)."""
    apy, err = _fetch_meth_apy_defillama(timeout)
    if apy is not None:
        return apy, None

    # DeFiLlama failed — try direct mETH endpoints
    apy2, err2 = _fetch_meth_apy_direct(timeout)
    if apy2 is not None:
        return apy2, None

    combined = "; ".join(filter(None, [err, err2]))
    log.warning("mETH APY fetch failed: %s", combined)
    return None, combined


def _fetch_gas_gwei(timeout: float) -> tuple[float | None, str | None]:
    """Fetch eth_gasPrice from Mantle mainnet RPC. Returns (gwei_float, error_msg)."""
    body = json.dumps({
        "jsonrpc": "2.0",
        "method": "eth_gasPrice",
        "params": [],
        "id": 1,
    }).encode()
    try:
        payload = _fetch_json(_MANTLE_RPC, timeout=timeout, body=body, method="POST")
        hex_val = payload.get("result")
        if not hex_val:
            msg = f"eth_gasPrice: missing result in {payload}"
            log.warning(msg)
            return None, msg
        wei = int(hex_val, 16)
        gwei = wei / 1e9
        return gwei, None
    except Exception as exc:
        msg = f"eth_gasPrice: {exc}"
        log.warning("Mantle RPC gas fetch failed: %s", msg)
        return None, msg


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def fetch_mantle_signal(timeout: float = 8.0) -> MantleSignal:
    """Fetch Mantle on-chain signals. Never raises — errors surface in .error."""
    fetched_at = datetime.now(timezone.utc).isoformat()
    source = "mantle_mainnet_rpc + meth_api"

    meth_apy, err_meth = _fetch_meth_apy(timeout)
    gas_gwei, err_gas = _fetch_gas_gwei(timeout)

    errors = [e for e in (err_meth, err_gas) if e]
    error = "; ".join(errors) if errors else None

    return MantleSignal(
        meth_apy=meth_apy,
        gas_price_gwei=gas_gwei,
        fetched_at=fetched_at,
        source=source,
        error=error,
    )
