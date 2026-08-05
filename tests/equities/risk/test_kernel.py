"""Tests for RiskKernel fuses."""
import pytest

from core.assets.instrument import CapTier, Instrument
from equities.risk.kernel import RiskKernel, SizedRecommendation
from equities.strategy import Recommendation, Sleeve


def _rec(
    ticker: str = "ARWR",
    entry: float = 74.0,
    stop: float = 68.0,
    tp: float = 88.0,
) -> Recommendation:
    return Recommendation(
        instrument=Instrument(ticker, ticker, "NASDAQ", CapTier.SMALL),
        sleeve=Sleeve.SWING,
        side="buy",
        entry=entry,
        stop_loss=stop,
        take_profit=tp,
        size_pct=0.02,
        confidence=0.72,
        catalyst="test",
        thesis="test thesis",
        horizon="2 weeks",
    )


def _open_pos(ticker: str = "X", shares: float = 10.0, price: float = 50.0) -> dict:
    return {"ticker": ticker, "sleeve": "swing", "shares": shares, "entry_price": price, "status": "open"}


def _swing_rec(
    ticker: str = "ARWR",
    entry: float = 100.0,
    stop_loss: float = 95.0,
    take_profit: float = 115.0,
    size_pct: float = 0.02,
    confidence: float = 0.72,
) -> Recommendation:
    """Swing Recommendation factory keyed to the R:R / sizing gate tests below.

    Default take_profit=115 clears the 2:1 min_rr gate for entry=100/stop=95
    (rr=3.0) so tests targeting the sizing scale, not the R:R gate, don't
    need to think about asymmetry unless they override take_profit.
    """
    return Recommendation(
        instrument=Instrument(ticker, ticker, "NASDAQ", CapTier.SMALL),
        sleeve=Sleeve.SWING,
        side="buy",
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        size_pct=size_pct,
        confidence=confidence,
        catalyst="test",
        thesis="test thesis",
        horizon="2 weeks",
    )


@pytest.fixture
def make_swing_rec():
    return _swing_rec


@pytest.fixture
def kernel_factory():
    """Callable[..., RiskKernel]; capital/max_name_pct default large enough that the
    max-position-size cap never clips the share-count ratios these tests assert on."""
    def _factory(**kwargs) -> RiskKernel:
        params = {"capital": 100_000.0, "max_name_pct": 1.0}
        params.update(kwargs)
        return RiskKernel(**params)
    return _factory


@pytest.fixture
def kernel_and_rec_factory(kernel_factory, make_swing_rec):
    # capital=100_000, risk_pct=0.02, min_rr=2.0 (kernel default)
    kernel = kernel_factory(risk_pct=0.02)
    return kernel, make_swing_rec


def test_approves_valid_recommendation():
    kernel = RiskKernel(capital=1000.0)
    result = kernel.approve(_rec(), open_positions=[])
    assert result.approved is True
    assert result.shares > 0


def test_rejects_when_max_positions_reached():
    kernel = RiskKernel(capital=1000.0, max_positions=2)
    open_pos = [_open_pos("A"), _open_pos("B")]
    result = kernel.approve(_rec(), open_positions=open_pos)
    assert result.approved is False
    assert "max_positions" in result.rejection_reason


def test_rejects_when_daily_loss_exceeded():
    kernel = RiskKernel(capital=1000.0, daily_loss_limit_pct=0.05)
    result = kernel.approve(_rec(), open_positions=[], today_realized_loss=-100.0)
    assert result.approved is False
    assert "daily_loss" in result.rejection_reason


def test_rejects_on_drawdown():
    kernel = RiskKernel(capital=1000.0, drawdown_limit_pct=0.15)
    # current equity 800 → drawdown = 20% > 15%
    result = kernel.approve(_rec(), open_positions=[], current_equity=800.0)
    assert result.approved is False
    assert "drawdown" in result.rejection_reason


def test_circuit_breaker_stays_halted():
    kernel = RiskKernel(capital=1000.0, drawdown_limit_pct=0.10)
    kernel.approve(_rec(), open_positions=[], current_equity=880.0)  # trips breaker
    result = kernel.approve(_rec(), open_positions=[])
    assert result.approved is False
    assert "circuit_breaker" in result.rejection_reason


def test_shares_positive_on_valid_input():
    # min_rr=0: this rec keeps the default tp=88.0 (below entry=100), which
    # only pre-dates the R:R gate — not what this test is exercising.
    kernel = RiskKernel(capital=10_000.0, risk_pct=0.01, min_rr=0)
    result = kernel.approve(_rec(entry=100.0, stop=90.0), open_positions=[])
    assert result.approved is True
    assert result.shares > 0


def test_rejects_missing_stop_loss():
    kernel = RiskKernel(capital=1000.0)
    rec = _rec()
    # Manually create a recommendation with no stop
    import dataclasses
    no_stop = dataclasses.replace(rec, stop_loss=None)
    result = kernel.approve(no_stop, open_positions=[])
    assert result.approved is False


def test_min_rr_gate_rejects_poor_asymmetry(kernel_and_rec_factory):
    kernel, make_rec = kernel_and_rec_factory  # construct kernel with min_rr=2.0
    # risk $5, reward $2.50 -> rr 0.5 -> reject
    bad = make_rec(entry=100.0, stop_loss=95.0, take_profit=102.5)
    sized = kernel.approve(bad, [], today_realized_loss=0.0, current_equity=100_000)
    assert not sized.approved
    assert "rr_" in (sized.rejection_reason or "")

    # risk $5, reward $12 -> rr 2.4 -> passes the gate
    good = make_rec(entry=100.0, stop_loss=95.0, take_profit=112.0)
    sized = kernel.approve(good, [], today_realized_loss=0.0, current_equity=100_000)
    assert sized.approved


def test_size_pct_scales_swing_risk(kernel_and_rec_factory):
    """AGGRESSIVE (0.04) sizes 2x the GRADUAL baseline (0.02); NIBBLE (0.01) sizes 0.5x."""
    kernel, make_rec = kernel_and_rec_factory  # capital=100_000, risk_pct=0.02
    rec_gradual = make_rec(entry=100.0, stop_loss=95.0, size_pct=0.02)
    rec_aggressive = make_rec(entry=100.0, stop_loss=95.0, size_pct=0.04)
    rec_nibble = make_rec(entry=100.0, stop_loss=95.0, size_pct=0.01)

    s_gradual = kernel.approve(rec_gradual, [], today_realized_loss=0.0, current_equity=100_000)
    s_aggr = kernel.approve(rec_aggressive, [], today_realized_loss=0.0, current_equity=100_000)
    s_nibble = kernel.approve(rec_nibble, [], today_realized_loss=0.0, current_equity=100_000)

    assert s_aggr.shares == pytest.approx(2.0 * s_gradual.shares, rel=1e-6)
    assert s_nibble.shares == pytest.approx(0.5 * s_gradual.shares, rel=1e-6)


def test_kelly_used_only_with_sufficient_band_history(kernel_factory, make_swing_rec):
    rich = kernel_factory(risk_pct=0.02, kelly_fraction=0.5, kelly_min_trades=30,
                          win_stats_lookup=lambda conf: (40, 0.6), min_rr=0)
    poor = kernel_factory(risk_pct=0.02, kelly_fraction=0.5, kelly_min_trades=30,
                          win_stats_lookup=lambda conf: (5, 0.9), min_rr=0)
    rec = make_swing_rec(entry=100.0, stop_loss=95.0, take_profit=110.0, size_pct=0.02)
    s_rich = rich.approve(rec, [], today_realized_loss=0.0, current_equity=100_000)
    s_poor = poor.approve(rec, [], today_realized_loss=0.0, current_equity=100_000)
    # b = 10/5 = 2, p = 0.6 -> kelly risk = 0.5*0.4 = 0.20, clamped to 2x base = 0.04
    # poor history -> base path risk 0.02. Rich sizes exactly 2x poor.
    assert s_rich.shares == pytest.approx(2.0 * s_poor.shares, rel=1e-6)


# --- Core DCA concentration cap ------------------------------------------
# Regression: the core branch returned before every concentration check, so the
# sleeve doing the actual accumulating had no per-name ceiling. Repeated DCA
# adds took single names past max_name_pct while the cap reported itself as
# enforced (NVDA 26.5%, META 26.4% against a stated 25% limit).

def _core_rec(ticker: str = "NVDA", entry: float = 200.0, size_pct: float = 0.05) -> Recommendation:
    return Recommendation(
        instrument=Instrument(ticker, ticker, "NASDAQ", CapTier.LARGE),
        sleeve=Sleeve.CORE,
        side="buy",
        entry=entry,
        stop_loss=None,
        take_profit=None,
        size_pct=size_pct,
        confidence=0.72,
        catalyst="dca",
        thesis="quality accumulation",
        horizon="months",
    )


def _core_pos(ticker: str, shares: float, price: float, sleeve: str = "core") -> dict:
    return {"ticker": ticker, "sleeve": sleeve, "shares": shares, "entry_price": price, "status": "open"}


def test_core_dca_fresh_name_is_approved():
    kernel = RiskKernel(capital=100_000.0, max_name_pct=0.25)
    result = kernel.approve(_core_rec(), open_positions=[])
    assert result.approved
    assert result.shares == pytest.approx(25.0)


def test_core_dca_add_beyond_name_cap_is_rejected():
    kernel = RiskKernel(capital=100_000.0, max_name_pct=0.25)
    held = [_core_pos("NVDA", shares=120.0, price=200.0)]  # 24% already
    result = kernel.approve(_core_rec(), open_positions=held)  # +5% would breach
    assert not result.approved
    assert "concentration_cap" in result.rejection_reason


def test_core_dca_counts_exposure_across_sleeves():
    """One ticker held in both sleeves is a single concentration risk."""
    kernel = RiskKernel(capital=100_000.0, max_name_pct=0.25)
    mixed = [
        _core_pos("NVDA", shares=60.0, price=200.0, sleeve="core"),
        _core_pos("NVDA", shares=60.0, price=200.0, sleeve="swing"),
    ]
    result = kernel.approve(_core_rec(), open_positions=mixed)
    assert not result.approved


def test_core_dca_cap_is_per_name_not_portfolio_wide():
    kernel = RiskKernel(capital=100_000.0, max_name_pct=0.25)
    held = [_core_pos("NVDA", shares=120.0, price=200.0)]
    result = kernel.approve(_core_rec(ticker="AAPL"), open_positions=held)
    assert result.approved


# --- Gross exposure cap -------------------------------------------------


def test_gross_cap_rejects_when_book_fully_deployed():
    """At 1.0x gross the kernel must refuse to draw on broker margin."""
    kernel = RiskKernel(capital=100_000.0, max_gross_pct=1.0, max_positions=99)
    book = [_open_pos(f"T{i}", shares=100.0, price=100.0) for i in range(10)]  # $100k gross
    result = kernel.approve(_rec(), book)
    assert not result.approved
    assert "gross_exposure" in result.rejection_reason


def test_gross_cap_clamps_partial_headroom():
    """With $5k headroom the order is sized down, not rejected."""
    kernel = RiskKernel(capital=100_000.0, max_gross_pct=1.0, max_positions=99)
    book = [_open_pos(f"T{i}", shares=100.0, price=100.0) for i in range(9)]
    book.append(_open_pos("T9", shares=50.0, price=100.0))  # $95k gross
    result = kernel.approve(_rec(entry=100.0, stop=95.0, tp=115.0), book)
    assert result.approved
    assert result.shares * 100.0 <= 5_000.0 + 1e-6


def test_gross_cap_counts_core_sleeve_too():
    """Core DCA exposure consumes the same ceiling as swing."""
    kernel = RiskKernel(capital=100_000.0, max_gross_pct=1.0, max_positions=99)
    book = [{"ticker": f"C{i}", "sleeve": "core", "shares": 100.0, "entry_price": 100.0,
             "status": "open"} for i in range(10)]
    result = kernel.approve(_rec(), book)
    assert not result.approved
    assert "gross_exposure" in result.rejection_reason


def test_gross_cap_above_one_permits_leverage():
    """max_gross_pct=1.5 is the deliberate leverage knob."""
    kernel = RiskKernel(capital=100_000.0, max_gross_pct=1.5, max_positions=99)
    book = [_open_pos(f"T{i}", shares=100.0, price=100.0) for i in range(10)]
    result = kernel.approve(_rec(entry=100.0, stop=95.0, tp=115.0), book)
    assert result.approved
    assert result.shares > 0
