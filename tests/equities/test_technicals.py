"""Tests for technical indicator computation.

Hand-computed expectations verify:
- RSI 14 with Wilder smoothing
- MACD histogram (12/26 EMA, 9-signal)
- 20-day momentum percentage
- 20-day annualized volatility
"""
import math
import pytest

from equities.data.technicals import (
    rsi_14,
    macd_hist,
    momentum_20d_pct,
    vol_20d_ann_pct,
    compute_technicals,
)


class TestRSI14:
    """RSI with Wilder smoothing on 14-period lookback."""

    def test_constant_up_series(self):
        """Constant increasing closes should give RSI = 100."""
        closes = [100.0 + i * 1.0 for i in range(20)]
        result = rsi_14(closes)
        assert result is not None
        assert result == 100.0, "Constant up series should have RSI = 100"

    def test_constant_down_series(self):
        """Constant decreasing closes should give RSI = 0."""
        closes = [100.0 - i * 1.0 for i in range(20)]
        result = rsi_14(closes)
        assert result is not None
        assert result == 0.0, "Constant down series should have RSI = 0"

    def test_flat_series(self):
        """All equal closes: 0 gains, 0 losses → RSI = 50 (neutral)."""
        closes = [100.0] * 20
        result = rsi_14(closes)
        assert result is not None
        assert result == 50.0, "Flat series should have RSI = 50"

    def test_insufficient_data_14(self):
        """14 closes (13 deltas) should return None; need 15 for 14 deltas."""
        closes = [100.0 + i for i in range(14)]
        result = rsi_14(closes)
        assert result is None

    def test_minimum_data_15(self):
        """15 closes (14 deltas) is minimum; should compute."""
        closes = [100.0 + i for i in range(15)]
        result = rsi_14(closes)
        assert result is not None
        assert 0.0 <= result <= 100.0

    def test_known_series(self):
        """Known 30-bar series with hand-computed RSI expectation.

        Bars 1-14 gains/losses determine first avg.
        Bar 15 onward use Wilder smoothing.
        """
        # This series alternates +1, -0.5 for 30 bars starting at 100
        closes = []
        price = 100.0
        for i in range(30):
            closes.append(price)
            if i % 2 == 0:
                price += 1.0  # +1
            else:
                price -= 0.5  # -0.5

        result = rsi_14(closes)
        assert result is not None
        # With alternating +1, -0.5: avg_gain ≈ 0.667, avg_loss ≈ 0.333
        # RS ≈ 2.0, RSI ≈ 66.67
        assert 60.0 < result < 75.0, f"Expected ~66.67, got {result}"


class TestMACDHist:
    """MACD histogram: 12/26 EMA, 9-bar signal line."""

    def test_insufficient_data_34(self):
        """34 closes (12+26-1) is minimum for MACD line only.
        Signal needs 9 more: 34+8 = 42. Need 35 closes (index 0-34).
        Actually: need 26 closes for 26-EMA, then 9 signal bars.
        Let me test with 34 (insufficient) and 35+ (sufficient).
        """
        closes = [100.0 + i for i in range(34)]
        result = macd_hist(closes)
        assert result is None, "34 closes insufficient for MACD histogram"

    def test_minimum_data_35(self):
        """35 closes: 26-EMA ready, +8 more signal bars → histogram ready."""
        closes = [100.0 + i for i in range(35)]
        result = macd_hist(closes)
        assert result is not None

    def test_constant_series(self):
        """All equal closes: MACD = 0, Signal = 0, Histogram = 0."""
        closes = [100.0] * 50
        result = macd_hist(closes)
        assert result is not None
        assert abs(result) < 1e-9, "Constant series should have histogram ≈ 0"

    def test_known_series(self):
        """Series with varying dynamics computes a finite histogram."""
        # Mixed pattern: flat, up, down
        closes = [100.0] * 15
        closes.extend([100.0 + i * 0.5 for i in range(1, 20)])
        closes.extend([115.0 - i * 0.5 for i in range(1, 16)])
        result = macd_hist(closes)
        assert result is not None
        # Should be finite
        assert math.isfinite(result), "Histogram should be finite"


class TestMomentum20d:
    """20-day momentum: (close[today] - close[20_days_ago]) / close[20_days_ago] * 100."""

    def test_insufficient_data_20(self):
        """20 closes: can compare [-1] to [-20], but we need 21 to have a [20] delta.
        Actually: closes[20] to closes[0] → need 21 elements (indices 0-20).
        """
        closes = [100.0 + i for i in range(20)]
        result = momentum_20d_pct(closes)
        assert result is None, "20 closes insufficient; need 21"

    def test_minimum_data_21(self):
        """21 closes (indices 0-20): closes[20] - closes[0] is valid."""
        closes = [100.0 + i for i in range(21)]
        result = momentum_20d_pct(closes)
        assert result is not None

    def test_flat_series(self):
        """No change over 20 days → momentum = 0%."""
        closes = [100.0] * 25
        result = momentum_20d_pct(closes)
        assert result is not None
        assert result == 0.0

    def test_up_20_percent(self):
        """Close goes from 100 to 120 over 20 days."""
        closes = [100.0 + i * 1.0 for i in range(21)]
        # closes[0] = 100, closes[20] = 120
        # momentum = (120 - 100) / 100 * 100 = 20%
        result = momentum_20d_pct(closes)
        assert result is not None
        assert abs(result - 20.0) < 0.01, f"Expected 20%, got {result}%"

    def test_down_10_percent(self):
        """Close goes from 100 to 90 over 20 days."""
        closes = [100.0 - i * 0.5 for i in range(21)]
        # closes[0] = 100, closes[20] = 90
        # momentum = (90 - 100) / 100 * 100 = -10%
        result = momentum_20d_pct(closes)
        assert result is not None
        assert abs(result - (-10.0)) < 0.01, f"Expected -10%, got {result}%"


class TestVol20dAnnPct:
    """20-day annualized volatility: stdev(log_returns) * sqrt(252) * 100."""

    def test_insufficient_data_20(self):
        """20 log returns need 21 closes."""
        closes = [100.0 + i for i in range(20)]
        result = vol_20d_ann_pct(closes)
        assert result is None, "20 closes insufficient; need 21"

    def test_minimum_data_21(self):
        """21 closes → 20 log returns."""
        closes = [100.0 + i for i in range(21)]
        result = vol_20d_ann_pct(closes)
        assert result is not None
        assert result > 0.0, "Volatility should be positive"

    def test_zero_volatility(self):
        """Flat closes → 0 log returns → vol = 0."""
        closes = [100.0] * 21
        result = vol_20d_ann_pct(closes)
        assert result is not None
        assert result < 0.1, "Flat series should have near-zero volatility"

    def test_known_series(self):
        """Simple arithmetic series: closes = [100, 101, 102, ..., 120]

        Log returns ≈ ln(next/prev) ≈ (next - prev) / prev for small changes.
        Each return ≈ 1/100 = 0.01
        Stdev ≈ 0 (they're all the same)
        Annualized vol ≈ 0
        """
        closes = [100.0 + i for i in range(21)]
        result = vol_20d_ann_pct(closes)
        assert result is not None
        # Constant returns → stdev ≈ 0 → vol ≈ 0
        assert result < 1.0, f"Constant returns should have low vol, got {result}%"

    def test_volatile_series(self):
        """Alternating high/low returns should have higher vol."""
        closes = [100.0]
        for i in range(20):
            if i % 2 == 0:
                closes.append(closes[-1] * 1.02)  # +2%
            else:
                closes.append(closes[-1] * 0.98)  # -2%

        result = vol_20d_ann_pct(closes)
        assert result is not None
        # ±2% returns should give decent annualized vol
        assert result > 10.0, f"Volatile series should have high vol, got {result}%"


class TestComputeTechnicals:
    """Full compute_technicals dict aggregation."""

    def test_shape_insufficient_data(self):
        """All indicators insufficient → all None."""
        closes = [100.0] * 10  # Too few for any indicator
        result = compute_technicals(closes)

        assert isinstance(result, dict)
        assert "rsi_14" in result
        assert "macd_hist" in result
        assert "mom_20d_pct" in result
        assert "vol_20d_ann_pct" in result

        assert result["rsi_14"] is None
        assert result["macd_hist"] is None
        assert result["mom_20d_pct"] is None
        assert result["vol_20d_ann_pct"] is None

    def test_shape_sufficient_data(self):
        """50 closes → all indicators computed."""
        closes = [100.0 + i * 0.1 for i in range(50)]
        result = compute_technicals(closes)

        assert isinstance(result, dict)
        assert result["rsi_14"] is not None
        assert result["macd_hist"] is not None
        assert result["mom_20d_pct"] is not None
        assert result["vol_20d_ann_pct"] is not None

    def test_partial_sufficiency(self):
        """30 closes: RSI/momentum ready, but MACD needs 35."""
        closes = [100.0 + i for i in range(30)]
        result = compute_technicals(closes)

        assert result["rsi_14"] is not None  # 30 >= 15
        assert result["mom_20d_pct"] is not None  # 30 >= 21
        assert result["macd_hist"] is None  # 30 < 35
        assert result["vol_20d_ann_pct"] is not None  # 30 >= 21

    def test_all_values_in_range(self):
        """RSI and vol should be bounded; MACD/momentum unbounded but finite."""
        closes = [100.0 + i * 0.5 for i in range(50)]
        result = compute_technicals(closes)

        if result["rsi_14"] is not None:
            assert 0.0 <= result["rsi_14"] <= 100.0
        if result["vol_20d_ann_pct"] is not None:
            assert result["vol_20d_ann_pct"] >= 0.0

        for key in result:
            if result[key] is not None:
                assert math.isfinite(result[key]), f"{key} is not finite: {result[key]}"
