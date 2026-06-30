"""Tests for the Open Cabinet executive disclosure provider."""
from __future__ import annotations

import json
from datetime import date

from equities.data.executive_disclosures import ExecutiveDisclosureProvider


def _payload() -> bytes:
    return json.dumps({
        "exportedAt": "2026-06-18T23:14:42.541Z",
        "officials": [{
            "name": "Kratsios, Michael J",
            "slug": "kratsios-michael-j",
            "mostRecentFilingDate": "2026-04-17T04:20:00",
            "transactions": [
                {
                    "description": "iShares Core Dividend Growth ETF",
                    "ticker": "DGRO",
                    "type": "Purchase",
                    "date": "2026-03-09",
                    "amount": "$15,001-$50,000",
                    "lateFilingFlag": False,
                },
                {
                    "description": "Municipal bond",
                    "ticker": None,
                    "type": "Purchase",
                    "date": "2026-03-10",
                    "amount": "$1,001-$15,000",
                    "lateFilingFlag": False,
                },
                {
                    "description": "Old holding",
                    "ticker": "OLD",
                    "type": "Sale",
                    "date": "2025-01-01",
                    "amount": "$1,001-$15,000",
                    "lateFilingFlag": True,
                },
            ],
        }],
    }).encode()


def test_fetch_normalizes_recent_ticker_transactions(monkeypatch):
    monkeypatch.setattr(
        "equities.data.executive_disclosures._fetch_bytes",
        lambda url, timeout: _payload(),
    )

    result = ExecutiveDisclosureProvider(lookback_days=45).fetch()

    assert result.error is None
    assert result.source == "open_cabinet"
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.ticker == "DGRO"
    assert trade.politician == "Kratsios, Michael J"
    assert trade.chamber == "executive"
    assert trade.transaction_type == "buy"
    assert trade.amount_min == 15_001
    assert trade.amount_max == 50_000
    assert trade.transaction_date == date(2026, 3, 9)
    assert trade.date_filed == date(2026, 4, 17)
    assert trade.filing_lag_days == 39
    assert trade.source_url.endswith("/officials/kratsios-michael-j")


def test_fetch_never_raises(monkeypatch):
    def fail(url, timeout):
        raise OSError("offline")

    monkeypatch.setattr("equities.data.executive_disclosures._fetch_bytes", fail)

    result = ExecutiveDisclosureProvider().fetch()

    assert result.trades == []
    assert result.source == "open_cabinet"
    assert "offline" in result.error
