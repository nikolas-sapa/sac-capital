"""The technical gate must fail closed when the price feed degrades.

Regression: a rate-limited run returned empty frames for the whole universe.
Every candidate then had no technical evidence, and the runner passed all of
them through ungated (138 vs 5 on a healthy run).
"""
from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from core.assets.instrument import CapTier, Instrument
from equities.data.prices import YFinancePriceFeed
from equities.screen.event_screen import CandidateEvent, EventType
from equities.screen.relative_strength import ScreeningCoverage
from runner_equities import (
    _apply_tech_gate,
    _keep_candidate_without_technicals,
    _tech_coverage_ok,
)


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


class TestSharedTechGate:
    """Every timing-checked screen must reach the same verdict for a ticker.

    Regression: politician candidates were appended after the gate ran, so a
    name dropped as do_not_chase on the filings path re-entered ungated.
    """

    @staticmethod
    def _candidate(ticker: str):
        return CandidateEvent(
            instrument=Instrument(ticker, ticker, "NASDAQ", CapTier.MID),
            event_type=EventType.POLITICIAN_DISCLOSURE,
            evidence="POL buy",
            urgency=0.65,
        )

    @staticmethod
    def _coverage(failed=None):
        return ScreeningCoverage(total=10, screened=10, failed=failed or {})

    def test_do_not_chase_is_dropped(self):
        evidence = SimpleNamespace(
            evidence="RS rank 3/190", trend_ok=True, base_ok=True,
            breakout_volume=False, do_not_chase=True,
        )
        kept = _apply_tech_gate(
            [self._candidate("ENTG")], {"ENTG": evidence}, self._coverage(), hard_gate=True
        )
        assert kept == []

    def test_clean_technicals_survive_and_are_annotated(self):
        evidence = SimpleNamespace(
            evidence="RS rank 3/190", trend_ok=True, base_ok=True,
            breakout_volume=False, do_not_chase=False,
        )
        kept = _apply_tech_gate(
            [self._candidate("BWXT")], {"BWXT": evidence}, self._coverage(), hard_gate=True
        )
        assert len(kept) == 1
        assert "Technicals: RS rank 3/190" in kept[0].evidence

    def test_data_outage_drops_politician_candidate(self):
        kept = _apply_tech_gate(
            [self._candidate("MU")], {}, self._coverage({"MU": "empty_frame"}), hard_gate=True
        )
        assert kept == []


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
