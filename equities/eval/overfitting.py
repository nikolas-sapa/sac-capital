"""Overfitting diagnostics for the variant-selection tournament.

Selecting the best of N backtested variants without correcting for the number
of trials manufactures fake edges — the "best" trial is often just the trial
that got luckiest. This module implements, clean-room from Bailey & Lopez de
Prado (numpy + stdlib only, no external stats deps):

- ``pbo``: Probability of Backtest Overfitting via combinatorially-symmetric
  cross-validation (CSCV). "Bailey, D. and M. Lopez de Prado (2014),
  'The Probability of Backtest Overfitting'."
- ``probabilistic_sharpe`` / ``deflated_sharpe``: PSR / DSR, correcting the
  Sharpe ratio for non-normal returns (skew/kurtosis) and for selection bias
  across multiple trials. "Bailey, D. and M. Lopez de Prado (2014),
  'The Deflated Sharpe Ratio'."

``verdict`` combines both into a single pass/fail gate the promoter consumes.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Any, Callable, Sequence

import numpy as np

_EULER_MASCHERONI = 0.5772156649015329


# ----------------------------------------------------------------------
# Small stats helpers (no scipy) — normal CDF / inverse CDF, moments.
# ----------------------------------------------------------------------

def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF (Acklam's rational approximation)."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    p_low = 0.02425
    p_high = 1.0 - p_low
    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
               (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)


def _sharpe_ratio(returns: np.ndarray) -> float:
    """Per-period (non-annualized) Sharpe: mean / population std."""
    std = float(np.std(returns, ddof=0))
    if std == 0.0:
        return 0.0
    return float(np.mean(returns)) / std


def _skewness(returns: np.ndarray) -> float:
    """Sample skewness (population moments, m3 / m2^1.5)."""
    m2 = float(np.mean((returns - returns.mean()) ** 2))
    if m2 == 0.0:
        return 0.0
    m3 = float(np.mean((returns - returns.mean()) ** 3))
    return m3 / m2 ** 1.5


def _kurtosis(returns: np.ndarray) -> float:
    """Sample kurtosis, non-excess (population moments, m4 / m2^2; normal = 3)."""
    m2 = float(np.mean((returns - returns.mean()) ** 2))
    if m2 == 0.0:
        return 3.0
    m4 = float(np.mean((returns - returns.mean()) ** 4))
    return m4 / m2 ** 2


# ----------------------------------------------------------------------
# PBO — combinatorially-symmetric cross-validation
# ----------------------------------------------------------------------

def pbo(
    trial_returns_matrix: Any,
    n_groups: int = 10,
    metric: Callable[[np.ndarray], float] | None = None,
) -> float:
    """Probability of Backtest Overfitting via CSCV.

    Args:
        trial_returns_matrix: 2D array-like, rows = periods, columns = trials.
        n_groups: Number of equal-sized time slices to split periods into
            (must be even; rounded down to the nearest even number, capped at
            the number of periods).
        metric: fn(returns_1d) -> float performance score. Defaults to the
            per-period Sharpe ratio.

    Returns:
        PBO in [0, 1] — the fraction of CSCV combinations where the trial
        selected as best in-sample ranks at or below the out-of-sample
        median. High PBO (> 0.5) means the "winner" is indistinguishable
        from luck.
    """
    M = np.asarray(trial_returns_matrix, dtype=float)
    if M.ndim != 2:
        raise ValueError("trial_returns_matrix must be 2D (periods x trials)")
    n_periods, n_trials = M.shape
    if n_trials < 2:
        raise ValueError("pbo needs at least 2 trials to compare")
    if n_periods < 2:
        raise ValueError("pbo needs at least 2 periods")

    metric = metric or _sharpe_ratio

    n_groups = min(n_groups, n_periods)
    if n_groups % 2 != 0:
        n_groups -= 1
    n_groups = max(n_groups, 2)

    groups = np.array_split(np.arange(n_periods), n_groups)

    lambdas: list[float] = []
    for train_group_idx in itertools.combinations(range(n_groups), n_groups // 2):
        test_group_idx = [g for g in range(n_groups) if g not in train_group_idx]
        train_rows = np.concatenate([groups[g] for g in train_group_idx])
        test_rows = np.concatenate([groups[g] for g in test_group_idx])

        train_perf = np.array([metric(M[train_rows, j]) for j in range(n_trials)])
        test_perf = np.array([metric(M[test_rows, j]) for j in range(n_trials)])

        n_star = int(np.argmax(train_perf))
        # Relative rank of the in-sample winner within the OOS performance
        # distribution (1 = worst .. n_trials = best).
        rank = int(np.sum(test_perf < test_perf[n_star])) + 1
        rc = rank / (n_trials + 1)
        rc = min(max(rc, 1e-6), 1 - 1e-6)
        lam = math.log(rc / (1.0 - rc))
        lambdas.append(lam)

    lambdas_arr = np.array(lambdas)
    return float(np.mean(lambdas_arr <= 0.0))


# ----------------------------------------------------------------------
# PSR / DSR
# ----------------------------------------------------------------------

def probabilistic_sharpe(returns: Any, benchmark_sr: float = 0.0) -> float:
    """Probability that the true Sharpe ratio exceeds `benchmark_sr`.

    Corrects the standard Sharpe-ratio significance test for skewed/
    fat-tailed returns (Bailey & Lopez de Prado, 2012).
    """
    r = np.asarray(returns, dtype=float)
    n = r.size
    if n < 2:
        raise ValueError("probabilistic_sharpe needs at least 2 observations")

    sr = _sharpe_ratio(r)
    skew = _skewness(r)
    kurt = _kurtosis(r)

    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2
    denom = math.sqrt(max(denom, 1e-12))
    z = (sr - benchmark_sr) * math.sqrt(n - 1) / denom
    return _norm_cdf(z)


def deflated_sharpe(returns: Any, all_trial_sharpes: Any) -> float:
    """Deflated Sharpe Ratio: PSR benchmarked against the expected maximum
    Sharpe ratio one would observe by chance over `len(all_trial_sharpes)`
    independent trials (Bailey & Lopez de Prado, 2014).
    """
    sharpes = np.asarray(all_trial_sharpes, dtype=float)
    n_trials = sharpes.size
    if n_trials < 1:
        raise ValueError("deflated_sharpe needs at least 1 trial Sharpe ratio")

    if n_trials > 1:
        sigma_sr = float(np.std(sharpes, ddof=1))
    else:
        sigma_sr = 0.0

    if sigma_sr <= 0.0 or n_trials <= 1:
        sr0 = 0.0
    else:
        sr0 = sigma_sr * (
            (1.0 - _EULER_MASCHERONI) * _norm_ppf(1.0 - 1.0 / n_trials)
            + _EULER_MASCHERONI * _norm_ppf(1.0 - 1.0 / (n_trials * math.e))
        )

    return probabilistic_sharpe(returns, benchmark_sr=sr0)


# ----------------------------------------------------------------------
# Verdict
# ----------------------------------------------------------------------

def verdict(
    trial_returns_matrix: Any,
    *,
    max_pbo: float = 0.5,
    min_dsr: float = 0.95,
    n_groups: int = 10,
) -> dict[str, Any]:
    """Evaluate overfitting risk across a full set of tournament trials.

    The "winner" trial is the column with the highest per-period Sharpe
    ratio — DSR/PSR are reported for that trial, but PBO is computed over
    the entire matrix, not just the winner.

    Args:
        trial_returns_matrix: 2D array-like, rows = periods, columns = trials.
        max_pbo: Reject if PBO >= this (default 0.5).
        min_dsr: Reject unless DSR > this (default 0.95).
        n_groups: CSCV time-slice count, passed through to `pbo`.

    Returns:
        {"pbo": float, "dsr": float, "psr": float, "passed": bool, "reason": str}
    """
    M = np.asarray(trial_returns_matrix, dtype=float)
    sharpes = [_sharpe_ratio(M[:, j]) for j in range(M.shape[1])]
    best_col = int(np.argmax(sharpes))
    winner_returns = M[:, best_col]

    p = pbo(M, n_groups=n_groups)
    dsr = deflated_sharpe(winner_returns, sharpes)
    psr = probabilistic_sharpe(winner_returns)

    pbo_ok = p < max_pbo
    dsr_ok = dsr > min_dsr
    passed = pbo_ok and dsr_ok

    if passed:
        reason = "passed_overfitting_check"
    elif not pbo_ok and not dsr_ok:
        reason = f"pbo={p:.3f}>=max_pbo={max_pbo} and dsr={dsr:.3f}<=min_dsr={min_dsr}"
    elif not pbo_ok:
        reason = f"pbo={p:.3f}>=max_pbo={max_pbo}"
    else:
        reason = f"dsr={dsr:.3f}<=min_dsr={min_dsr}"

    return {"pbo": p, "dsr": dsr, "psr": psr, "passed": passed, "reason": reason}


@dataclass(frozen=True)
class OverfittingChecker:
    """Constructor-configurable wrapper around `verdict` for reuse across
    repeated tournament runs (mirrors the KillGate/AutoPromoter pattern).
    """

    max_pbo: float = 0.5
    min_dsr: float = 0.95
    n_groups: int = 10

    def evaluate(self, trial_returns_matrix: Any) -> dict[str, Any]:
        return verdict(
            trial_returns_matrix,
            max_pbo=self.max_pbo,
            min_dsr=self.min_dsr,
            n_groups=self.n_groups,
        )


if __name__ == "__main__":
    # Self-check: PBO should be high (~overfit) on pure-noise trials, and low
    # on a set of trials containing one genuinely-persistent signal. A single
    # draw is noisy (CSCV over a finite sample has real sampling variance),
    # so average over several independent draws rather than asserting on one
    # seed.
    n_draws = 8

    # Pure noise: 50 trials, all iid N(0, 1), over only 60 periods. With many
    # trials relative to little data, multiple-comparison overfitting bias
    # dominates — no trial has any real edge, so "the best one" is overfit by
    # construction (PBO trends toward/above 0.5 as trials grow relative to
    # sample size; DSR correctly refuses to bless the lucky winner).
    noise_pbos: list[float] = []
    last_noise_verdict: dict | None = None
    for seed in range(n_draws):
        rng = np.random.default_rng(seed)
        noise_matrix = rng.normal(0.0, 1.0, size=(60, 50))
        noise_pbos.append(pbo(noise_matrix, n_groups=10))
        last_noise_verdict = verdict(noise_matrix)

    # Genuine signal: 4 noise trials + 1 trial with a real, persistent
    # positive drift over a longer sample — a small, honest trial count with
    # enough data for the true edge to dominate estimation noise.
    signal_pbos: list[float] = []
    last_signal_verdict: dict | None = None
    for seed in range(n_draws):
        rng = np.random.default_rng(seed)
        noise_matrix = rng.normal(0.0, 1.0, size=(500, 4))
        signal_col = rng.normal(0.35, 1.0, size=500)
        signal_matrix = np.column_stack([noise_matrix, signal_col])
        signal_pbos.append(pbo(signal_matrix, n_groups=10))
        last_signal_verdict = verdict(signal_matrix)

    mean_noise_pbo = sum(noise_pbos) / n_draws
    mean_signal_pbo = sum(signal_pbos) / n_draws
    print(f"mean pure-noise PBO ({n_draws} draws) = {mean_noise_pbo:.3f}")
    print(f"mean signal PBO     ({n_draws} draws) = {mean_signal_pbo:.3f}")
    print(f"pure-noise verdict (last draw) = {last_noise_verdict}")
    print(f"signal verdict     (last draw) = {last_signal_verdict}")

    assert mean_noise_pbo > 0.5, f"expected high mean PBO on pure noise, got {mean_noise_pbo:.3f}"
    assert mean_signal_pbo < mean_noise_pbo, "a persistent signal should lower mean PBO vs pure noise"
    assert not last_noise_verdict["passed"], "pure noise must not pass the overfitting gate"
    assert last_signal_verdict["passed"], "a persistent, dominant signal should pass the gate"

    print("OK: overfitting.py self-check passed")
