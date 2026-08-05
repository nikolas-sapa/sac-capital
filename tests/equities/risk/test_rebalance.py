"""Concentration cap must be enforced on held positions, not only at entry."""
import pytest

from equities.risk.rebalance import compute_trims


def _pos(ticker, market_value, shares, sleeve="core"):
    return {"ticker": ticker, "market_value": market_value, "shares": shares, "sleeve": sleeve}


class TestComputeTrims:
    def test_position_within_cap_is_untouched(self):
        assert compute_trims([_pos("MSFT", 15_000, 30)], equity=100_000, max_name_pct=0.25) == []

    def test_position_inside_band_does_not_churn(self):
        # 25.5% with a 1pp band -> leave it alone.
        assert compute_trims([_pos("NVDA", 25_500, 100)], equity=100_000, max_name_pct=0.25) == []

    def test_overweight_position_is_trimmed_to_the_cap(self):
        trims = compute_trims([_pos("NVDA", 26_500, 100)], equity=100_000, max_name_pct=0.25)
        assert len(trims) == 1
        t = trims[0]
        assert t.ticker == "NVDA"
        # price 265/sh; excess 1_500 -> 5.660377 shares
        assert t.shares == pytest.approx(5.660377, abs=1e-5)
        assert t.notional == pytest.approx(1_500.0)
        assert t.target_weight == pytest.approx(0.25)

    def test_trim_lands_exactly_on_the_cap(self):
        trims = compute_trims([_pos("NVDA", 40_000, 100)], equity=100_000, max_name_pct=0.25)
        remaining_value = 40_000 - trims[0].shares * 400.0
        assert remaining_value == pytest.approx(25_000.0)

    def test_aggregates_holdings_across_sleeves(self):
        """Same ticker in two sleeves is one concentration risk."""
        positions = [
            _pos("NVDA", 14_000, 50, sleeve="core"),
            _pos("NVDA", 14_000, 50, sleeve="swing"),
        ]
        trims = compute_trims(positions, equity=100_000, max_name_pct=0.25)
        assert len(trims) == 1
        assert trims[0].notional == pytest.approx(3_000.0)

    def test_never_closes_a_position_outright(self):
        # Cap so small the maths would sell everything -> refuse.
        trims = compute_trims([_pos("NVDA", 26_500, 100)], equity=100_000, max_name_pct=0.0001)
        assert trims == []

    def test_multiple_overweight_names(self):
        positions = [
            _pos("NVDA", 28_135, 132.7),
            _pos("META", 28_014, 47.6),
            _pos("LLY", 16_234, 14.4),
        ]
        trims = compute_trims(positions, equity=106_020, max_name_pct=0.25)
        assert {t.ticker for t in trims} == {"NVDA", "META"}

    def test_skips_dust_trims(self):
        trims = compute_trims(
            [_pos("NVDA", 25_000.50, 100)], equity=100_000, max_name_pct=0.25,
            band=0.0, min_notional=1.0,
        )
        assert trims == []

    def test_zero_equity_is_safe(self):
        assert compute_trims([_pos("NVDA", 26_500, 100)], equity=0, max_name_pct=0.25) == []

    def test_ignores_shorts_and_empty_rows(self):
        positions = [_pos("NVDA", -5_000, -10), _pos("", 30_000, 10), _pos("MU", 0, 0)]
        assert compute_trims(positions, equity=100_000, max_name_pct=0.25) == []

    def test_large_overweight_is_clamped_not_dumped(self):
        """A big overweight converges over runs instead of one huge order."""
        trims = compute_trims([_pos("NVDA", 60_000, 100)], equity=100_000, max_name_pct=0.25)
        assert len(trims) == 1
        assert trims[0].shares == pytest.approx(50.0)  # clamped to 50% of 100
        assert trims[0].target_weight == pytest.approx(0.30)  # short of cap, by design

    def test_implausible_cap_is_refused(self):
        """A cap this low is misconfiguration; obeying it would liquidate."""
        assert compute_trims([_pos("NVDA", 26_500, 100)], equity=100_000, max_name_pct=0.01) == []
