import numpy as np

from equities.eval.overfitting import (
    OverfittingChecker,
    deflated_sharpe,
    pbo,
    probabilistic_sharpe,
    verdict,
)


def test_pbo_high_on_pure_noise():
    # Many trials, little data → the in-sample "winner" is overfit by
    # construction. Average over draws since a single draw is noisy.
    pbos = []
    for seed in range(8):
        rng = np.random.default_rng(seed)
        noise_matrix = rng.normal(0.0, 1.0, size=(60, 50))
        pbos.append(pbo(noise_matrix, n_groups=10))
    assert sum(pbos) / len(pbos) > 0.5


def test_pbo_low_on_persistent_signal():
    # A genuine, persistent edge among a handful of noise trials should
    # consistently rank best out-of-sample too → low PBO.
    pbos = []
    for seed in range(8):
        rng = np.random.default_rng(seed)
        noise = rng.normal(0.0, 1.0, size=(500, 4))
        signal = rng.normal(0.35, 1.0, size=500)
        matrix = np.column_stack([noise, signal])
        pbos.append(pbo(matrix, n_groups=10))
    assert sum(pbos) / len(pbos) < 0.1


def test_verdict_rejects_pure_noise():
    rng = np.random.default_rng(1)
    noise_matrix = rng.normal(0.0, 1.0, size=(60, 50))
    result = verdict(noise_matrix)
    assert result["passed"] is False
    assert "pbo" in result and "dsr" in result and "psr" in result
    assert result["reason"]


def test_verdict_accepts_persistent_signal():
    rng = np.random.default_rng(1)
    noise = rng.normal(0.0, 1.0, size=(500, 4))
    signal = rng.normal(0.35, 1.0, size=500)
    matrix = np.column_stack([noise, signal])
    result = verdict(matrix)
    assert result["passed"] is True
    assert result["reason"] == "passed_overfitting_check"


def test_verdict_thresholds_are_configurable():
    rng = np.random.default_rng(1)
    noise_matrix = rng.normal(0.0, 1.0, size=(60, 50))
    lenient = verdict(noise_matrix, max_pbo=1.0, min_dsr=-1.0)
    assert lenient["passed"] is True

    checker = OverfittingChecker(max_pbo=1.0, min_dsr=-1.0)
    assert checker.evaluate(noise_matrix)["passed"] is True


def test_deflated_sharpe_penalizes_more_trials():
    rng = np.random.default_rng(3)
    returns = rng.normal(0.1, 1.0, size=200)
    few_trial_sharpes = rng.normal(0.0, 0.1, size=3)
    many_trial_sharpes = rng.normal(0.0, 0.1, size=200)
    # More trials → higher bar for "SR0" → lower (or equal) DSR.
    assert deflated_sharpe(returns, many_trial_sharpes) <= deflated_sharpe(returns, few_trial_sharpes)


def test_probabilistic_sharpe_bounded():
    rng = np.random.default_rng(4)
    returns = rng.normal(0.05, 1.0, size=100)
    psr = probabilistic_sharpe(returns)
    assert 0.0 <= psr <= 1.0
