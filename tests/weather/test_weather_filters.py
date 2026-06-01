from core.markets import Outcome
from strategies.weather.filters import passes_filters


def _outcomes(asks: list[float]) -> list[Outcome]:
    return [Outcome(token_id=f"t{i}", label=f"bin{i}", best_bid=a - 0.05, best_ask=a)
            for i, a in enumerate(asks)]


def test_passes_when_sum_below_095():
    assert passes_filters(_outcomes([0.28, 0.30, 0.30])) is True  # sum=0.88


def test_rejects_when_sum_above_095():
    assert passes_filters(_outcomes([0.33, 0.33, 0.33])) is False  # sum=0.99 > 0.95


def test_rejects_when_any_bin_below_001():
    assert passes_filters(_outcomes([0.005, 0.30, 0.30])) is False


def test_rejects_when_any_bin_above_045():
    assert passes_filters(_outcomes([0.46, 0.25, 0.25])) is False


def test_exactly_045_is_ok():
    assert passes_filters(_outcomes([0.45, 0.25, 0.20])) is True  # sum=0.90
