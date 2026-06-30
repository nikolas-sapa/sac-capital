"""Candidate screen for lagged supply-chain paper strategies."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from core.assets.bar import PriceSeries
from equities.research.lag_rules import (
    above_smas,
    bar_on_or_before,
    is_chased,
    lag_features,
    makes_period_high,
    return_pct,
    stop_from_atr,
)
from equities.research.supply_chain import SUPPLY_CHAIN, BottleneckScorer, get_trunks_for_leaf


SEMI_BOTTLENECK_UNIVERSE = frozenset({
    "AMAT", "LRCX", "ENTG", "KLAC", "ASML", "ONTO", "KLIC", "AMKR", "COHR", "MU",
})

STRATEGY_SEMI_BOTTLENECK = "semi_bottleneck_catch_up"
STRATEGY_MULTI_TRUNK = "multi_trunk_supplier_confirmation"
STRATEGY_POST_BREAKOUT = "post_trunk_breakout_leaf_lag"


class HistoryProvider(Protocol):
    def history(self, ticker: str, period: str = "1y", interval: str = "1d") -> PriceSeries: ...


@dataclass(frozen=True)
class SupplyChainLagCandidate:
    strategy: str
    ticker: str
    trunk: str
    entry_signal_at: date
    features: dict[str, float | int | str | bool | list[str]]
    entry_rule: str
    exit_rule: str
    risk_tags: list[str]
    thesis: str

    @property
    def opportunity_score(self) -> float:
        value = self.features.get("opportunity_score", 0.0)
        return float(value) if isinstance(value, int | float) else 0.0


class SupplyChainLagScreen:
    def __init__(self, prices: HistoryProvider, period: str = "1y") -> None:
        self._prices = prices
        self._period = period
        self._cache: dict[str, PriceSeries] = {}
        self._scorer = BottleneckScorer()

    def scan(self, as_of: date | None = None) -> list[SupplyChainLagCandidate]:
        candidates = (
            self.scan_semi_bottleneck(as_of)
            + self.scan_multi_trunk(as_of)
            + self.scan_post_breakout(as_of)
        )
        return sorted(candidates, key=lambda c: c.opportunity_score, reverse=True)

    def scan_history(
        self,
        *,
        start_after_bars: int = 252,
        reserve_exit_bars: int = 31,
        step_bars: int = 5,
        calendar_ticker: str = "SPY",
    ) -> list[SupplyChainLagCandidate]:
        calendar = self._series(calendar_ticker)
        end = max(start_after_bars, len(calendar.bars) - reserve_exit_bars)
        candidates: list[SupplyChainLagCandidate] = []
        for idx in range(start_after_bars, end, step_bars):
            candidates.extend(self.scan(as_of=calendar.bars[idx].day))
        return sorted(candidates, key=lambda c: c.opportunity_score, reverse=True)

    def scan_semi_bottleneck(self, as_of: date | None = None) -> list[SupplyChainLagCandidate]:
        candidates: list[SupplyChainLagCandidate] = []
        for trunk in ("AMD", "TSM", "NVDA"):
            trunk_series = self._series(trunk)
            for leaf in SUPPLY_CHAIN.get(trunk, []):
                if leaf not in SEMI_BOTTLENECK_UNIVERSE:
                    continue
                leaf_series = self._series(leaf)
                aligned = self._aligned_indexes((trunk_series, leaf_series), as_of)
                if aligned is None:
                    continue
                signal_day, (trunk_idx, leaf_idx) = aligned
                features = lag_features(
                    trunk,
                    leaf,
                    trunk_series,
                    leaf_series,
                    trunk_end_index=trunk_idx,
                    leaf_end_index=leaf_idx,
                )
                if features is None:
                    continue
                if not (
                    features.lag_1y >= 25.0
                    and features.lag_3mo >= 10.0
                    and features.lag_1mo >= -5.0
                    and features.bottleneck_score >= 0.50
                    and features.opportunity_score >= 0.18
                ):
                    continue
                if is_chased(leaf_series, end_index=leaf_idx):
                    continue
                signal_bar = leaf_series.bars[leaf_idx]
                stop_loss = stop_from_atr(signal_bar.close, leaf_series, end_index=leaf_idx)
                candidates.append(SupplyChainLagCandidate(
                    strategy=STRATEGY_SEMI_BOTTLENECK,
                    ticker=leaf,
                    trunk=trunk,
                    entry_signal_at=signal_day,
                    features={
                        "lag_1y": features.lag_1y,
                        "lag_3mo": features.lag_3mo,
                        "lag_1mo": features.lag_1mo,
                        "bottleneck_score": features.bottleneck_score,
                        "opportunity_score": features.opportunity_score,
                        "stop_loss": stop_loss,
                        "take_profit": round(signal_bar.close * 1.18, 4),
                        "max_holding_days": 21,
                    },
                    entry_rule="weekly close after lag signal; next session fill in backtest",
                    exit_rule="+18%, ATR stop capped at -8%, 21 trading days, or trunk 20d return < -10%",
                    risk_tags=["crowding", "trunk_reversal", "supplier_chase_filter"],
                    thesis=f"{leaf} is a bottleneck supplier lagging {trunk} despite upstream strength.",
                ))
        return candidates

    def scan_multi_trunk(self, as_of: date | None = None) -> list[SupplyChainLagCandidate]:
        qqq = self._series("QQQ")
        leaves = sorted({leaf for chain in SUPPLY_CHAIN.values() for leaf in chain})
        candidates: list[SupplyChainLagCandidate] = []
        for leaf in leaves:
            trunks = get_trunks_for_leaf(leaf)
            if len(trunks) < 2:
                continue
            leaf_series = self._series(leaf)
            active: list[tuple[str, float, float, float, date]] = []
            for trunk in trunks:
                trunk_series = self._series(trunk)
                aligned = self._aligned_indexes((qqq, trunk_series, leaf_series), as_of)
                if aligned is None:
                    continue
                signal_day, (qqq_idx, trunk_idx, leaf_idx) = aligned
                qqq_3mo = return_pct(qqq, 63, end_index=qqq_idx)
                trunk_3mo = return_pct(trunk_series, 63, end_index=trunk_idx)
                features = lag_features(
                    trunk,
                    leaf,
                    trunk_series,
                    leaf_series,
                    trunk_end_index=trunk_idx,
                    leaf_end_index=leaf_idx,
                )
                if qqq_3mo is None or trunk_3mo is None or features is None:
                    continue
                if trunk_3mo > qqq_3mo + 10.0:
                    active.append((trunk, features.lag_3mo, features.lag_1mo, features.bottleneck_score, signal_day))
            if len(active) < 2:
                continue
            avg_lag_3mo = sum(row[1] for row in active) / len(active)
            one_positive_1mo = any(row[2] >= 0.0 for row in active)
            min_bottleneck = min(row[3] for row in active)
            if not (avg_lag_3mo >= 15.0 and one_positive_1mo and min_bottleneck >= 0.45):
                continue
            signal_day = min(row[4] for row in active)
            leaf_idx = bar_on_or_before(leaf_series, signal_day)
            if leaf_idx is None or is_chased(leaf_series, end_index=leaf_idx):
                continue
            signal_bar = leaf_series.bars[leaf_idx]
            primary = max(active, key=lambda row: row[1])[0]
            active_trunks = [row[0] for row in active]
            candidates.append(SupplyChainLagCandidate(
                strategy=STRATEGY_MULTI_TRUNK,
                ticker=leaf,
                trunk=primary,
                entry_signal_at=signal_day,
                features={
                    "active_trunk_count": len(active),
                    "active_trunks": active_trunks,
                    "avg_lag_3mo": round(avg_lag_3mo, 4),
                    "min_bottleneck_score": round(min_bottleneck, 4),
                    "opportunity_score": round((avg_lag_3mo / 100.0) * min_bottleneck, 4),
                    "stop_loss": round(signal_bar.close * 0.90, 4),
                    "take_profit": round(signal_bar.close * 1.20, 4),
                    "max_holding_days": 30,
                },
                entry_rule="2+ active trunks outperform QQQ by 10pp; next session fill in backtest",
                exit_rule="+20%, -10%, 30 trading days, or active trunk count < 1",
                risk_tags=["single_ai_factor", "multi_trunk_overlap", "supplier_chase_filter"],
                thesis=f"{leaf} has confirmed demand pull from multiple active trunks: {', '.join(active_trunks)}.",
            ))
        return candidates

    def scan_post_breakout(self, as_of: date | None = None) -> list[SupplyChainLagCandidate]:
        candidates: list[SupplyChainLagCandidate] = []
        for trunk, leaves in SUPPLY_CHAIN.items():
            trunk_series = self._series(trunk)
            for leaf in leaves:
                leaf_series = self._series(leaf)
                aligned = self._aligned_indexes((trunk_series, leaf_series), as_of)
                if aligned is None:
                    continue
                signal_day, (trunk_idx, leaf_idx) = aligned
                trunk_20d = return_pct(trunk_series, 20, end_index=trunk_idx)
                if (
                    trunk_20d is None
                    or trunk_20d < 15.0
                    or not makes_period_high(trunk_series, 63, end_index=trunk_idx)
                ):
                    continue
                leaf_20d = return_pct(leaf_series, 20, end_index=leaf_idx)
                leaf_3d = return_pct(leaf_series, 3, end_index=leaf_idx)
                if leaf_20d is None or leaf_20d > 8.0:
                    continue
                if leaf_3d is not None and leaf_3d > 10.0:
                    continue
                if not above_smas(leaf_series, (50, 200), end_index=leaf_idx):
                    continue
                bottleneck = self._scorer.score(leaf, trunk)
                if bottleneck < 0.50:
                    continue
                signal_bar = leaf_series.bars[leaf_idx]
                candidates.append(SupplyChainLagCandidate(
                    strategy=STRATEGY_POST_BREAKOUT,
                    ticker=leaf,
                    trunk=trunk,
                    entry_signal_at=signal_day,
                    features={
                        "trunk_20d_return": round(trunk_20d, 4),
                        "leaf_20d_return": round(leaf_20d, 4),
                        "leaf_3d_return": round(leaf_3d or 0.0, 4),
                        "bottleneck_score": bottleneck,
                        "entry_delay_days": 3,
                        "opportunity_score": round((trunk_20d - leaf_20d) / 100.0 * bottleneck, 4),
                        "stop_loss": round(signal_bar.close * 0.93, 4),
                        "take_profit": round(signal_bar.close * 1.12, 4),
                        "max_holding_days": 15,
                    },
                    entry_rule="trunk 63d high and 20d breakout; buy delayed leaf after 3 sessions",
                    exit_rule="+12%, -7%, 15 trading days, or trunk loses SMA20",
                    risk_tags=["momentum_whipsaw", "delayed_entry", "trunk_sma20_invalidation"],
                    thesis=f"{leaf} has not followed {trunk}'s fresh breakout despite supply-chain linkage.",
                ))
        return candidates

    def _series(self, ticker: str) -> PriceSeries:
        if ticker not in self._cache:
            try:
                self._cache[ticker] = self._prices.history(ticker, period=self._period)
            except Exception as exc:
                print(f"  [SCREEN] ticker={ticker} error={exc}")
                self._cache[ticker] = PriceSeries(ticker=ticker, bars=[])
        return self._cache[ticker]

    def _aligned_indexes(
        self,
        series: tuple[PriceSeries, ...],
        as_of: date | None,
    ) -> tuple[date, tuple[int, ...]] | None:
        if any(not item.bars for item in series):
            return None
        common_day = as_of or min(item.latest.day for item in series if item.latest is not None)
        indexes = tuple(bar_on_or_before(item, common_day) for item in series)
        if any(idx is None for idx in indexes):
            return None
        return common_day, indexes  # type: ignore[return-value]
