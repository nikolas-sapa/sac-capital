"""Tests for MacroRegimeGate — all yfinance calls stubbed."""
from __future__ import annotations

import pytest

from equities.data.macro_regime import MacroRegimeGate, RegimeSnapshot


def _make_gate(overrides: dict[str, list[float]]) -> MacroRegimeGate:
    defaults: dict[str, list[float]] = {
        "^VIX":     [18.0, 18.0],
        "^TNX":     [4.2, 4.2],
        "^IRX":     [3.5, 3.5],
        "HYG":      [77.0, 77.0, 77.0, 77.2, 77.3],
        "LQD":      [110.0, 110.0, 110.0, 110.1, 110.1],
        "DX-Y.NYB": [102.0, 102.0],
        "XLK": [100.0, 103.0],
        "XLF": [38.0, 39.0],
        "XLE": [85.0, 84.0],
        "XLV": [140.0, 141.0],
    }
    data = {**defaults, **overrides}

    def fetcher(ticker: str, period: str) -> list[float]:
        return data.get(ticker, [])

    return MacroRegimeGate(fetcher=fetcher)


def test_crisis_regime():
    gate = _make_gate({"^VIX": [35.0, 35.0]})
    snap = gate.classify()
    assert snap.regime == "crisis"
    assert snap.vix == pytest.approx(35.0)


def test_risk_off_elevated_vix():
    gate = _make_gate({"^VIX": [25.0, 25.0]})
    snap = gate.classify()
    assert snap.regime == "risk_off"


def test_risk_off_inverted_yield_curve():
    # VIX calm, but yield curve deeply inverted
    gate = _make_gate({"^VIX": [15.0, 15.0], "^TNX": [3.0, 3.0], "^IRX": [3.5, 3.5]})
    snap = gate.classify()
    assert snap.regime == "risk_off"
    assert snap.yield_curve == pytest.approx(-0.5)


def test_risk_on_regime():
    gate = _make_gate({
        "^VIX": [13.0, 13.0],
        "^TNX": [4.5, 4.5],
        "^IRX": [3.9, 3.9],  # yield curve = 0.6 > 0.5
        "HYG":  [77.0, 77.5],  # cs_trend positive
        "LQD":  [110.0, 110.0],
    })
    snap = gate.classify()
    assert snap.regime == "risk_on"


def test_neutral_regime():
    # VIX between 16-22, curve mildly positive, spreads stable
    gate = _make_gate({
        "^VIX": [18.0, 18.0],
        "^TNX": [4.0, 4.0],
        "^IRX": [3.7, 3.7],   # yield_curve = 0.3 (not > 0.5 for risk_on)
    })
    snap = gate.classify()
    assert snap.regime == "neutral"


def test_fetcher_error_defaults_neutral():
    def bad_fetcher(ticker: str, period: str) -> list[float]:
        raise RuntimeError("no network")

    gate = MacroRegimeGate(fetcher=bad_fetcher)
    snap = gate.classify()
    assert snap.regime == "neutral"


def test_snapshot_contains_sector_momentum():
    gate = _make_gate({})
    snap = gate.classify()
    assert "XLK" in snap.sector_momentum
    assert "XLF" in snap.sector_momentum
