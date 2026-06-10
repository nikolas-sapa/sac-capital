"""VIX regime gate — blocks new swing entries during high-fear market regimes."""
from __future__ import annotations

from equities.data.yfinance_utils import call_quietly


class VIXRegimeGate:
    """Fetch current VIX and determine whether new swing entries are permitted.

    Fails open (returns True) if VIX data is unavailable.
    """

    def __init__(self, threshold: float = 30.0) -> None:
        self._threshold = threshold

    def current_vix(self) -> float | None:
        try:
            import yfinance as yf
            data = call_quietly(lambda: yf.Ticker("^VIX").history(period="2d"))
            if data.empty:
                return None
            return float(data["Close"].iloc[-1])
        except Exception:
            return None

    def allow_new_entries(self) -> tuple[bool, float | None]:
        """Return (allowed, current_vix). Fails open when vix is None."""
        vix = self.current_vix()
        if vix is None:
            return True, None
        return vix < self._threshold, vix
