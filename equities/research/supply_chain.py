"""Static supply chain graph mapping trunk companies to leaf suppliers."""
from __future__ import annotations

from dataclasses import dataclass


SUPPLY_CHAIN: dict[str, list[str]] = {
    "NVDA": ["MU", "COHR", "AMKR", "ONTO", "KLIC", "FN", "APH", "ENTG", "LRCX", "KLAC", "VRT", "MPWR", "AMAT", "CLS", "ALAB", "MRVL", "SMCI", "DELL", "ANET", "ETN", "GEV", "CEG", "PWR"],
    "AMD":  ["MU", "AMKR", "COHR", "LRCX", "AMAT", "ALAB", "MRVL", "SMCI", "DELL"],
    "AVGO": ["AMKR", "COHR", "MU", "MRVL", "ALAB", "ANET", "APH"],
    "TSM":  ["ASML", "LRCX", "KLAC", "AMAT", "ENTG", "ONTO", "KLIC"],
    "LLY":  ["DOCS", "GEHC", "TEM", "HIMS"],
    "MSFT": ["NOW", "CRM", "CRWD", "DDOG"],
    "GOOGL":["VRT", "ETN", "GEV", "CEG", "PWR"],
    "AMZN": ["VRT", "ETN", "GEV", "CEG"],
}

_BOTTLENECK_META: dict[str, dict[str, float]] = {
    "MU":   {"market_share": 0.25, "switching_cost": 0.90, "lead_time_years": 3.0},
    "COHR": {"market_share": 0.30, "switching_cost": 0.80, "lead_time_years": 2.0},
    "AMKR": {"market_share": 0.15, "switching_cost": 0.70, "lead_time_years": 2.5},
    "ASML": {"market_share": 0.90, "switching_cost": 1.00, "lead_time_years": 5.0},
    "LRCX": {"market_share": 0.45, "switching_cost": 0.85, "lead_time_years": 3.0},
    "KLAC": {"market_share": 0.50, "switching_cost": 0.85, "lead_time_years": 3.0},
    "ENTG": {"market_share": 0.35, "switching_cost": 0.75, "lead_time_years": 2.0},
    "VRT":  {"market_share": 0.25, "switching_cost": 0.60, "lead_time_years": 1.5},
    "ONTO": {"market_share": 0.20, "switching_cost": 0.70, "lead_time_years": 2.0},
    "KLIC": {"market_share": 0.25, "switching_cost": 0.65, "lead_time_years": 1.5},
    "FN":   {"market_share": 0.30, "switching_cost": 0.70, "lead_time_years": 1.5},
    "APH":  {"market_share": 0.10, "switching_cost": 0.50, "lead_time_years": 1.0},
    "AMAT": {"market_share": 0.20, "switching_cost": 0.80, "lead_time_years": 3.0},
    "CLS":  {"market_share": 0.15, "switching_cost": 0.50, "lead_time_years": 1.0},
    "DOCS": {"market_share": 0.20, "switching_cost": 0.60, "lead_time_years": 1.0},
    "GEHC": {"market_share": 0.15, "switching_cost": 0.70, "lead_time_years": 2.0},
    "TEM":  {"market_share": 0.05, "switching_cost": 0.50, "lead_time_years": 1.0},
    "HIMS": {"market_share": 0.05, "switching_cost": 0.30, "lead_time_years": 0.5},
    "NOW":  {"market_share": 0.15, "switching_cost": 0.85, "lead_time_years": 2.0},
    "CRWD": {"market_share": 0.20, "switching_cost": 0.90, "lead_time_years": 2.0},
    "DDOG": {"market_share": 0.12, "switching_cost": 0.75, "lead_time_years": 1.5},
    "ETN":  {"market_share": 0.15, "switching_cost": 0.60, "lead_time_years": 2.0},
    "GEV":  {"market_share": 0.10, "switching_cost": 0.70, "lead_time_years": 3.0},
    "CEG":  {"market_share": 0.08, "switching_cost": 0.80, "lead_time_years": 5.0},
    "PWR":  {"market_share": 0.10, "switching_cost": 0.50, "lead_time_years": 1.0},
    "MPWR": {"market_share": 0.10, "switching_cost": 0.70, "lead_time_years": 1.5},
    "MRVL": {"market_share": 0.12, "switching_cost": 0.75, "lead_time_years": 2.0},
    "CRM":  {"market_share": 0.20, "switching_cost": 0.80, "lead_time_years": 2.0},
    "ALAB": {"market_share": 0.10, "switching_cost": 0.80, "lead_time_years": 2.0},
    "SMCI": {"market_share": 0.12, "switching_cost": 0.55, "lead_time_years": 1.0},
    "DELL": {"market_share": 0.18, "switching_cost": 0.50, "lead_time_years": 1.0},
    "ANET": {"market_share": 0.25, "switching_cost": 0.85, "lead_time_years": 2.0},
}

_DEFAULT_META = {"market_share": 0.05, "switching_cost": 0.40, "lead_time_years": 1.0}


@dataclass(frozen=True)
class SupplyChainNode:
    ticker: str
    trunk: str
    bottleneck_score: float
    discovery_lag_pct: float


def get_leaves_for_trunk(trunk: str) -> list[str]:
    return SUPPLY_CHAIN.get(trunk, [])


def get_trunks_for_leaf(leaf: str) -> list[str]:
    return [t for t, leaves in SUPPLY_CHAIN.items() if leaf in leaves]


class BottleneckScorer:
    """Score a leaf supplier's bottleneck strength (0.0-1.0).

    Score = market_share*0.35 + switching_cost*0.45 + lead_time_factor*0.20
    """

    def score(self, leaf: str, trunk: str) -> float:  # noqa: ARG002
        meta = _BOTTLENECK_META.get(leaf, _DEFAULT_META)
        raw = (
            meta["market_share"] * 0.35
            + meta["switching_cost"] * 0.45
            + min(1.0, meta["lead_time_years"] / 5.0) * 0.20
        )
        return round(min(1.0, raw), 4)
