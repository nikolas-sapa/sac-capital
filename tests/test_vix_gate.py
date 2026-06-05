"""Tests for VIXRegimeGate."""
from __future__ import annotations

from equities.data.vix import VIXRegimeGate


class _StubVIX(VIXRegimeGate):
    def __init__(self, val: float | None, threshold: float = 30.0) -> None:
        super().__init__(threshold=threshold)
        self._val = val

    def current_vix(self) -> float | None:
        return self._val


def test_low_vix_allows_entries():
    gate = _StubVIX(18.5)
    allowed, vix = gate.allow_new_entries()
    assert allowed is True
    assert vix == 18.5


def test_high_vix_blocks_entries():
    gate = _StubVIX(35.2)
    allowed, vix = gate.allow_new_entries()
    assert allowed is False
    assert vix == 35.2


def test_none_vix_fails_open():
    gate = _StubVIX(None)
    allowed, vix = gate.allow_new_entries()
    assert allowed is True
    assert vix is None


def test_custom_threshold():
    gate = _StubVIX(25.0, threshold=20.0)
    allowed, _ = gate.allow_new_entries()
    assert allowed is False
