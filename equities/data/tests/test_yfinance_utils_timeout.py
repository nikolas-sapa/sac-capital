"""Real hard-timeout check for call_with_timeout (bounds hanging yfinance calls)."""
import time

import pytest

from equities.data.yfinance_utils import call_with_timeout


def test_blocking_call_is_bounded_and_raises():
    """A genuinely blocking fn must be abandoned and raise TimeoutError fast."""
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        call_with_timeout(lambda: time.sleep(30), timeout=0.2)
    elapsed = time.monotonic() - start
    assert elapsed < 5, f"call_with_timeout did not bound the hang (took {elapsed:.1f}s)"


def test_fast_call_returns_value():
    assert call_with_timeout(lambda: 42, timeout=5) == 42
