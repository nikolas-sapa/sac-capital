import pytest
from strategies.weather.consensus import consensus, ConsensusResult


def test_tight_pair_uses_tightest_two():
    # Spread=2.5 (≤3), tightest pair ICON+GFS (spread=0.5), ECMWF is outlier
    r = consensus(icon=70.0, gfs=70.5, ecmwf=72.5)
    assert r is not None
    assert r.center == pytest.approx(70.25)
    assert r.outlier == "ecmwf"


def test_all_close_uses_mean_of_all():
    # All within 1°C — no outlier, mean of all three
    r = consensus(icon=70.0, gfs=70.5, ecmwf=70.8)
    assert r is not None
    assert r.center == pytest.approx((70.0 + 70.5 + 70.8) / 3, abs=0.01)
    assert r.outlier is None


def test_spread_above_3_returns_none():
    r = consensus(icon=70.0, gfs=73.5, ecmwf=74.0)
    assert r is None


def test_outlier_above_skews_upward():
    # ECMWF outlier is above the ICON+GFS center
    r = consensus(icon=70.0, gfs=70.5, ecmwf=72.5)
    assert r is not None
    assert r.outlier == "ecmwf"
    assert r.outlier_above is True


def test_outlier_below_flags_downward():
    r = consensus(icon=73.0, gfs=72.5, ecmwf=70.5)
    assert r is not None
    assert r.outlier == "ecmwf"
    assert r.outlier_above is False


def test_result_has_spread():
    r = consensus(icon=70.0, gfs=70.5, ecmwf=72.5)
    assert r is not None
    assert r.spread == pytest.approx(2.5)
