"""Pure technical indicator computation — stdlib only, no external dependencies.

Functions compute:
- RSI 14 (Wilder smoothing)
- MACD histogram (12/26 EMA, 9-signal)
- 20-day momentum percentage
- 20-day annualized volatility
"""
from __future__ import annotations

import math


def rsi_14(closes: list[float]) -> float | None:
    """RSI with Wilder smoothing on 14-period lookback.

    Args:
        closes: List of closing prices.

    Returns:
        RSI value 0-100, or None if insufficient data (<15 closes).
    """
    if len(closes) < 15:  # Need 14 deltas (15 closes)
        return None

    gains = []
    losses = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        if delta > 0:
            gains.append(delta)
            losses.append(0.0)
        elif delta < 0:
            gains.append(0.0)
            losses.append(abs(delta))
        else:
            gains.append(0.0)
            losses.append(0.0)

    # First 14 deltas (indices 1-14)
    first_gains = gains[:14]
    first_losses = losses[:14]
    sum_gains = sum(first_gains)
    sum_losses = sum(first_losses)

    avg_gain = sum_gains / 14.0
    avg_loss = sum_losses / 14.0

    # Wilder smoothing: exponential moving average with alpha = 1/14
    alpha = 1.0 / 14.0
    for i in range(14, len(gains)):
        avg_gain = avg_gain * (1.0 - alpha) + gains[i] * alpha
        avg_loss = avg_loss * (1.0 - alpha) + losses[i] * alpha

    # Compute RSI
    if avg_loss == 0.0:
        if avg_gain == 0.0:
            return 50.0  # Flat series
        return 100.0  # Only gains
    if avg_gain == 0.0:
        return 0.0  # Only losses

    rs = avg_gain / avg_loss
    rsi = 100.0 * rs / (1.0 + rs)
    return rsi


def _ema(values: list[float], span: int) -> list[float]:
    """Exponential moving average.

    Args:
        values: List of values.
        span: EMA span (e.g., 12 for 12-EMA).

    Returns:
        List of EMA values (same length as input).
    """
    if len(values) == 0:
        return []

    alpha = 2.0 / (span + 1.0)
    ema_values = []
    sma = sum(values[:span]) / span
    ema_values.append(sma)

    for i in range(span, len(values)):
        ema = values[i] * alpha + ema_values[-1] * (1.0 - alpha)
        ema_values.append(ema)

    return ema_values


def macd_hist(closes: list[float]) -> float | None:
    """MACD histogram: (12-EMA - 26-EMA) - 9-EMA_of_MACD.

    Args:
        closes: List of closing prices.

    Returns:
        MACD histogram value, or None if insufficient data (<35 closes).
    """
    # Need 26-EMA ready + 8 more bars for signal (9 MACD values total)
    # First 26 closes → 26-EMA at index 25
    # Then MACD line from index 25-33 (9 values)
    # Signal line at index 33
    # Total: 34 closes minimum, but use 35 to be safe
    if len(closes) < 35:
        return None

    # Compute 12-EMA
    ema_12_values = _ema(closes, 12)
    # Compute 26-EMA
    ema_26_values = _ema(closes, 26)

    # MACD line: 12-EMA - 26-EMA
    # Both EMAs start at index 0 of their results
    # ema_12 has values starting from index 0 (actually index 11 of closes)
    # ema_26 has values starting at index 0 (actually index 25 of closes)
    # Align: ema_26[0] = 26-EMA at closes[25]
    #        ema_12[14] = 12-EMA at closes[25]
    macd_values = []
    for i in range(len(ema_26_values)):
        if i < len(ema_12_values):
            macd_values.append(ema_12_values[i] - ema_26_values[i])

    # If macd_values has fewer than 9 values, we don't have enough for signal
    if len(macd_values) < 9:
        return None

    # Compute 9-EMA of MACD
    signal_values = _ema(macd_values, 9)
    if len(signal_values) == 0:
        return None

    # Histogram is the last MACD value minus last signal value
    histogram = macd_values[-1] - signal_values[-1]
    return histogram


def momentum_20d_pct(closes: list[float]) -> float | None:
    """20-day momentum: (current - 20_days_ago) / 20_days_ago * 100.

    Args:
        closes: List of closing prices (most recent last).

    Returns:
        Momentum percentage, or None if insufficient data (<21 closes).
    """
    if len(closes) < 21:  # Need closes[-1] and closes[-21]
        return None

    current = closes[-1]
    past = closes[-21]
    if past == 0.0:
        return None
    momentum = ((current - past) / past) * 100.0
    return momentum


def vol_20d_ann_pct(closes: list[float]) -> float | None:
    """20-day annualized volatility: stdev(log_returns) * sqrt(252) * 100.

    Args:
        closes: List of closing prices (most recent last).

    Returns:
        Annualized volatility percentage, or None if insufficient data (<21 closes).
    """
    if len(closes) < 21:  # Need 20 log returns
        return None

    # Compute 20 log returns
    log_returns = []
    for i in range(len(closes) - 20, len(closes)):
        prev_close = closes[i - 1]
        curr_close = closes[i]
        if prev_close <= 0.0 or curr_close <= 0.0:
            return None  # Invalid prices
        log_return = math.log(curr_close / prev_close)
        log_returns.append(log_return)

    # Compute standard deviation of log returns
    if len(log_returns) == 0:
        return None
    mean_return = sum(log_returns) / len(log_returns)
    variance = sum((r - mean_return) ** 2 for r in log_returns) / len(log_returns)
    stdev = math.sqrt(variance)

    # Annualize: stdev * sqrt(252) * 100 (252 trading days per year)
    annualized_vol = stdev * math.sqrt(252.0) * 100.0
    return annualized_vol


def compute_technicals(closes: list[float]) -> dict:
    """Compute all technical indicators.

    Args:
        closes: List of closing prices (most recent last).

    Returns:
        Dict with keys: "rsi_14", "macd_hist", "mom_20d_pct", "vol_20d_ann_pct".
        Values may be None if insufficient data.
    """
    return {
        "rsi_14": rsi_14(closes),
        "macd_hist": macd_hist(closes),
        "mom_20d_pct": momentum_20d_pct(closes),
        "vol_20d_ann_pct": vol_20d_ann_pct(closes),
    }
