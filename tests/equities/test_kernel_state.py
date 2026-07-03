"""Test kernel state persistence across restarts."""
from pathlib import Path

from equities.risk.kernel import RiskKernel


class FakeRecommendation:
    """Minimal recommendation stub for testing kernel approval."""

    def __init__(self):
        self.entry = 100.0
        self.stop_loss = 95.0
        self.size_pct = 0.02
        self.sleeve = None

    class Instrument:
        ticker = "TEST"

    instrument = Instrument()


def test_high_water_mark_survives_restart(tmp_path: Path):
    """Verify HWM persists when kernel is restarted."""
    state = tmp_path / "kernel_state.json"
    k1 = RiskKernel(capital=10_000, state_path=state)
    # Simulate equity climbing to 12k via approve() with current_equity param
    rec = FakeRecommendation()
    k1.approve(rec, [], current_equity=12_000)

    # Create new kernel with same state file — should restore HWM
    k2 = RiskKernel(capital=10_000, state_path=state)
    assert k2._high_water_mark == 12_000


def test_halted_flag_survives_restart(tmp_path: Path):
    """Verify halt flag persists when kernel is restarted."""
    state = tmp_path / "kernel_state.json"
    k1 = RiskKernel(capital=10_000, state_path=state)
    rec = FakeRecommendation()

    # Set HWM to 12k
    k1.approve(rec, [], current_equity=12_000)

    # Trigger halt: 10k / 12k = 16.7% drawdown (exceeds 15% default limit)
    result = k1.approve(rec, [], current_equity=10_000)
    assert not result.approved and "drawdown" in result.rejection_reason
    assert k1._halted

    # Create new kernel — should restore halted state
    k2 = RiskKernel(capital=10_000, state_path=state)
    assert k2._halted

    # Verify new approval is rejected due to restored halt
    result2 = k2.approve(rec, [], current_equity=10_000)
    assert not result2.approved and "circuit_breaker" in result2.rejection_reason
