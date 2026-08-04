"""The technical gate must fail closed when the price feed degrades.

Regression: a rate-limited run returned empty frames for the whole universe.
Every candidate then had no technical evidence, and the runner passed all of
them through ungated (138 vs 5 on a healthy run).
"""
from __future__ import annotations

import pandas as pd

from equities.data.prices import YFinancePriceFeed
from runner_equities import _keep_candidate_without_technicals, _tech_coverage_ok


class TestCoverageThreshold:
    def test_healthy_coverage_trusts_the_gate(self):
        assert _tech_coverage_ok(180, 191) is True

    def test_collapsed_coverage_is_not_trusted(self):
        assert _tech_coverage_ok(0, 191) is False

    def test_partial_degradation_is_not_trusted(self):
        assert _tech_coverage_ok(100, 191) is False

    def test_empty_universe_does_not_divide_by_zero(self):
        assert _tech_coverage_ok(0, 0) is True


class TestMissingTechnicals:
    def test_data_outage_drops_the_candidate(self):
        assert _keep_candidate_without_technicals("empty_frame", hard_gate=True) is False

    def test_young_stock_still_eligible(self):
        # Recent IPOs (CRWV, OKLO, CRCL) legitimately lack history.
        assert _keep_candidate_without_technicals("insufficient history", hard_gate=True) is True

    def test_gate_disabled_keeps_everything(self):
        assert _keep_candidate_without_technicals("empty_frame", hard_gate=False) is True


class TestPriceMemo:
    def test_successful_series_is_reused(self, monkeypatch):
        calls = []

        def fake_download(**kwargs):
            calls.append(kwargs["tickers"])
            return pd.DataFrame(
                {"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5], "Volume": [100]},
                index=pd.to_datetime(["2026-08-04"]),
            )

        monkeypatch.setattr("equities.data.prices.yf.download", fake_download)
        feed = YFinancePriceFeed(isolate_requests=False)
        first = feed.history("PLTR")
        second = feed.history("PLTR")

        assert len(calls) == 1, "second call should hit the memo"
        assert first.closes == second.closes == [1.5]

    def test_empty_result_is_never_memoized(self, monkeypatch):
        calls = []

        def fake_download(**kwargs):
            calls.append(kwargs["tickers"])
            return pd.DataFrame()

        monkeypatch.setattr("equities.data.prices.yf.download", fake_download)
        feed = YFinancePriceFeed(retries=0, isolate_requests=False)
        feed.history("PLTR")
        feed.history("PLTR")

        assert len(calls) == 2, "a failed fetch must stay retryable"
