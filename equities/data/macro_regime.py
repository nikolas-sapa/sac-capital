"""MacroRegimeGate — classifies current macro regime from 5 yfinance signals."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegimeSnapshot:
    regime: str          # crisis | risk_off | neutral | risk_on
    vix: float | None
    yield_curve: float | None   # TNX - IRX
    credit_spread: float | None # HYG / LQD ratio (higher = tighter / more risk-on)
    dxy: float | None
    sector_momentum: dict[str, float]  # XLK/XLF/XLE/XLV 4-week returns


class MacroRegimeGate:
    _TICKERS = ["^VIX", "^TNX", "^IRX", "HYG", "LQD", "DX-Y.NYB",
                "XLK", "XLF", "XLE", "XLV"]
    _SECTORS = ["XLK", "XLF", "XLE", "XLV"]

    def __init__(self, fetcher=None) -> None:
        self._fetcher = fetcher  # injectable stub; None → live yfinance

    def _fetch(self, ticker: str, period: str = "1mo") -> list[float]:
        if self._fetcher is not None:
            return self._fetcher(ticker, period)
        import yfinance as yf
        data = yf.download(ticker, period=period, progress=False, auto_adjust=True)
        if data.empty:
            return []
        return list(data["Close"].dropna().values.tolist())

    def _last(self, prices: list[float]) -> float | None:
        return prices[-1] if prices else None

    def _pct_change(self, prices: list[float]) -> float | None:
        if len(prices) < 2:
            return None
        return (prices[-1] - prices[0]) / prices[0]

    def classify(self) -> RegimeSnapshot:
        try:
            vix_prices = self._fetch("^VIX", "5d")
            tnx_prices = self._fetch("^TNX", "5d")
            irx_prices = self._fetch("^IRX", "5d")
            hyg_prices = self._fetch("HYG", "5d")
            lqd_prices = self._fetch("LQD", "5d")
            dxy_prices = self._fetch("DX-Y.NYB", "5d")

            vix = self._last(vix_prices)
            tnx = self._last(tnx_prices)
            irx = self._last(irx_prices)
            hyg = self._last(hyg_prices)
            lqd = self._last(lqd_prices)
            dxy = self._last(dxy_prices)

            yield_curve = (tnx - irx) if (tnx is not None and irx is not None) else None
            credit_spread = (hyg / lqd) if (hyg is not None and lqd is not None and lqd != 0) else None

            # 4-week credit spread momentum (positive = spread tightening / risk-on)
            hyg_month = self._fetch("HYG", "1mo")
            lqd_month = self._fetch("LQD", "1mo")
            if hyg_month and lqd_month and len(hyg_month) >= 2 and len(lqd_month) >= 2:
                cs_start = hyg_month[0] / lqd_month[0] if lqd_month[0] != 0 else None
                cs_end = hyg_month[-1] / lqd_month[-1] if lqd_month[-1] != 0 else None
                cs_trend = (cs_end - cs_start) if (cs_start is not None and cs_end is not None) else None
            else:
                cs_trend = None

            sector_momentum: dict[str, float] = {}
            for sym in self._SECTORS:
                prices = self._fetch(sym, "1mo")
                chg = self._pct_change(prices)
                if chg is not None:
                    sector_momentum[sym] = chg

            regime = self._classify_regime(vix, yield_curve, credit_spread, cs_trend)

        except Exception:
            regime = "neutral"
            vix = yield_curve = credit_spread = dxy = cs_trend = None
            sector_momentum = {}

        return RegimeSnapshot(
            regime=regime,
            vix=vix,
            yield_curve=yield_curve,
            credit_spread=credit_spread,
            dxy=dxy,
            sector_momentum=sector_momentum,
        )

    @staticmethod
    def _classify_regime(
        vix: float | None,
        yield_curve: float | None,
        credit_spread: float | None,
        cs_trend: float | None,
    ) -> str:
        # Crisis — VIX above 30
        if vix is not None and vix > 30:
            return "crisis"

        # Risk-off — any of: elevated VIX, inverted curve, or fast credit deterioration
        risk_off = False
        if vix is not None and vix > 22:
            risk_off = True
        if yield_curve is not None and yield_curve < -0.20:
            risk_off = True
        if cs_trend is not None and cs_trend < -0.01:  # HYG/LQD ratio dropping fast
            risk_off = True
        if risk_off:
            return "risk_off"

        # Risk-on — all green lights
        if (
            vix is not None and vix < 16
            and yield_curve is not None and yield_curve > 0.50
            and (cs_trend is None or cs_trend >= 0)
        ):
            return "risk_on"

        return "neutral"
