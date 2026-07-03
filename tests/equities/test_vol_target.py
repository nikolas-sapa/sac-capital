"""Tests for vol_target_shares shadow sizing."""
from __future__ import annotations

import pytest

from equities.risk.vol_target import vol_target_shares


class TestVolTargetShares:
    """Test vol_target_shares shadow sizing function."""

    def test_basic_sizing_with_vol_20_pct(self) -> None:
        """Fixed inputs: vol=20%, target=20%, capital=10000, entry=100 -> shares calc."""
        # vol_20d_ann_pct = 20.0
        # target_vol_pct = 20.0
        # Formula: frac = min(target / vol * 0.02, max_alloc)
        #          frac = min(20 / 20 * 0.02, 0.25) = min(0.02, 0.25) = 0.02
        #          alloc = 10000 * 0.02 = 200
        #          shares = 200 / 100 = 2.0
        result = vol_target_shares(
            entry=100.0,
            vol_20d_ann_pct=20.0,
            capital=10000.0,
            target_vol_pct=20.0,
            max_alloc_pct=0.25,
        )
        assert result == pytest.approx(2.0, rel=1e-5)

    def test_high_vol_capped_by_max_alloc(self) -> None:
        """When vol is very low (high ratio), cap should bind at max_alloc_pct."""
        # vol_20d_ann_pct = 5.0
        # target_vol_pct = 20.0
        # Formula: frac = min(20 / 5 * 0.02, 0.25) = min(0.08, 0.25) = 0.08
        #          alloc = 10000 * 0.08 = 800
        #          shares = 800 / 100 = 8.0
        result = vol_target_shares(
            entry=100.0,
            vol_20d_ann_pct=5.0,
            capital=10000.0,
            target_vol_pct=20.0,
            max_alloc_pct=0.25,
        )
        assert result == pytest.approx(8.0, rel=1e-5)

    def test_extremely_low_vol_hits_max_alloc(self) -> None:
        """When vol is extremely low, should hit hard cap at max_alloc_pct."""
        # vol_20d_ann_pct = 1.0
        # target_vol_pct = 20.0
        # Formula: frac = min(20 / 1 * 0.02, 0.25) = min(0.40, 0.25) = 0.25
        #          alloc = 10000 * 0.25 = 2500
        #          shares = 2500 / 100 = 25.0
        result = vol_target_shares(
            entry=100.0,
            vol_20d_ann_pct=1.0,
            capital=10000.0,
            target_vol_pct=20.0,
            max_alloc_pct=0.25,
        )
        assert result == pytest.approx(25.0, rel=1e-5)

    def test_none_when_vol_none(self) -> None:
        """Return None if vol is None."""
        result = vol_target_shares(
            entry=100.0,
            vol_20d_ann_pct=None,
            capital=10000.0,
        )
        assert result is None

    def test_none_when_vol_zero(self) -> None:
        """Return None if vol is 0."""
        result = vol_target_shares(
            entry=100.0,
            vol_20d_ann_pct=0.0,
            capital=10000.0,
        )
        assert result is None

    def test_none_when_vol_negative(self) -> None:
        """Return None if vol is negative."""
        result = vol_target_shares(
            entry=100.0,
            vol_20d_ann_pct=-5.0,
            capital=10000.0,
        )
        assert result is None

    def test_none_when_entry_zero(self) -> None:
        """Return None if entry is 0."""
        result = vol_target_shares(
            entry=0.0,
            vol_20d_ann_pct=20.0,
            capital=10000.0,
        )
        assert result is None

    def test_none_when_entry_negative(self) -> None:
        """Return None if entry is negative."""
        result = vol_target_shares(
            entry=-100.0,
            vol_20d_ann_pct=20.0,
            capital=10000.0,
        )
        assert result is None

    def test_low_entry_small_capital(self) -> None:
        """Fractional shares with low entry price and small capital."""
        # entry=10.0, capital=500, vol=20, target=20
        # frac = min(20/20 * 0.02, 0.25) = 0.02
        # alloc = 500 * 0.02 = 10
        # shares = 10 / 10 = 1.0
        result = vol_target_shares(
            entry=10.0,
            vol_20d_ann_pct=20.0,
            capital=500.0,
        )
        assert result == pytest.approx(1.0, rel=1e-5)

    def test_fractional_shares(self) -> None:
        """Fractional shares output."""
        # entry=123.45, capital=5000, vol=35
        # frac = min(20/35 * 0.02, 0.25) = min(0.01143, 0.25) = 0.01143
        # alloc = 5000 * 0.01143 = 57.14
        # shares = 57.14 / 123.45 ≈ 0.463
        result = vol_target_shares(
            entry=123.45,
            vol_20d_ann_pct=35.0,
            capital=5000.0,
            target_vol_pct=20.0,
        )
        assert result is not None
        assert result > 0.0
        assert result < 1.0  # fractional

    def test_custom_target_vol(self) -> None:
        """Custom target vol percentage."""
        # target_vol_pct=30.0, vol=20, entry=100, capital=10000
        # frac = min(30/20 * 0.02, 0.25) = min(0.03, 0.25) = 0.03
        # alloc = 10000 * 0.03 = 300
        # shares = 300 / 100 = 3.0
        result = vol_target_shares(
            entry=100.0,
            vol_20d_ann_pct=20.0,
            capital=10000.0,
            target_vol_pct=30.0,
        )
        assert result == pytest.approx(3.0, rel=1e-5)

    def test_custom_max_alloc(self) -> None:
        """Custom max allocation percentage."""
        # vol=5, target=20, capital=10000, entry=100, max_alloc=0.10
        # frac = min(20/5 * 0.02, 0.10) = min(0.08, 0.10) = 0.08
        # alloc = 10000 * 0.08 = 800
        # shares = 800 / 100 = 8.0
        result = vol_target_shares(
            entry=100.0,
            vol_20d_ann_pct=5.0,
            capital=10000.0,
            target_vol_pct=20.0,
            max_alloc_pct=0.10,
        )
        assert result == pytest.approx(8.0, rel=1e-5)
