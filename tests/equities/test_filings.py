from __future__ import annotations

import sys
from types import ModuleType

from equities.data import filings as filings_mod


class _Response:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_recent_uses_cached_company_ticker_map(monkeypatch):
    filings_mod._company_ticker_map.cache_clear()
    filings_mod._ticker_to_cik.cache_clear()

    monkeypatch.setattr(
        filings_mod,
        "_company_ticker_map",
        lambda: {"AAPL": 320193},
    )

    calls: list[str] = []

    # Dates relative to today so the test does not rot: recent 8-K inside the
    # 30-day window, older 10-Q outside it.
    from datetime import date, timedelta

    recent_date = (date.today() - timedelta(days=10)).isoformat()
    old_date = (date.today() - timedelta(days=45)).isoformat()

    def fake_get(url, headers=None, timeout=None):  # noqa: ANN001
        calls.append(url)
        if url.endswith("CIK0000320193.json"):
            return _Response(
                {
                    "filings": {
                        "recent": {
                            "form": ["8-K", "10-Q"],
                            "filingDate": [recent_date, old_date],
                            "items": ["2.02, 9.01", ""],
                        }
                    }
                }
            )
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(filings_mod, "_USER_AGENT", "test-agent")
    fake_httpx = ModuleType("httpx")
    fake_httpx.get = fake_get  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    client = filings_mod.SECEdgarFilings()
    filings = client.recent("AAPL", days=30)

    assert [f.form_type for f in filings] == ["8-K"]
    assert calls == [
        "https://data.sec.gov/submissions/CIK0000320193.json",
    ]


def test_recent_returns_fast_when_ticker_not_in_map(monkeypatch):
    filings_mod._company_ticker_map.cache_clear()
    filings_mod._ticker_to_cik.cache_clear()

    monkeypatch.setattr(filings_mod, "_company_ticker_map", lambda: {})

    client = filings_mod.SECEdgarFilings()
    calls = []
    assert client.recent("ZZZZ", days=30) == []
    assert calls == []


def test_sc13d_forms_pass_the_filter(monkeypatch):
    filings_mod._company_ticker_map.cache_clear()
    filings_mod._ticker_to_cik.cache_clear()

    monkeypatch.setattr(
        filings_mod,
        "_company_ticker_map",
        lambda: {"TEST": 999999},
    )

    def fake_get(url, headers=None, timeout=None):  # noqa: ANN001
        if url.endswith("CIK0000999999.json"):
            return _Response(
                {
                    "filings": {
                        "recent": {
                            "form": ["SC 13D", "SC 13D/A", "4"],
                            "filingDate": ["2026-07-10", "2026-07-11", "2026-07-11"],
                            "items": ["", "", ""],
                        }
                    }
                }
            )
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(filings_mod, "_USER_AGENT", "test-agent")
    fake_httpx = ModuleType("httpx")
    fake_httpx.get = fake_get  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    client = filings_mod.SECEdgarFilings()
    filings = client.recent("TEST", days=30)

    got = {f.form_type for f in filings}
    assert "SC 13D" in got and "SC 13D/A" in got and "4" not in got


def test_recent_handles_mismatched_list_lengths(monkeypatch, capsys):
    """Test that mismatched list lengths are logged and truncated safely."""
    filings_mod._company_ticker_map.cache_clear()
    filings_mod._ticker_to_cik.cache_clear()

    monkeypatch.setattr(
        filings_mod,
        "_company_ticker_map",
        lambda: {"ACME": 123456},
    )

    def fake_get(url, headers=None, timeout=None):  # noqa: ANN001
        if url.endswith("CIK0000123456.json"):
            return _Response(
                {
                    "filings": {
                        "recent": {
                            "form": ["8-K", "10-Q", "10-K"],  # 3 items
                            "filingDate": ["2026-06-28", "2026-06-25"],  # 2 items (mismatch)
                            "items": ["2.02", ""],  # 2 items
                        }
                    }
                }
            )
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(filings_mod, "_USER_AGENT", "test-agent")
    fake_httpx = ModuleType("httpx")
    fake_httpx.get = fake_get  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    client = filings_mod.SECEdgarFilings()
    filings = client.recent("ACME", days=30)

    # Should truncate to the shortest (2 items) and log warning
    assert len(filings) == 2
    captured = capsys.readouterr()
    assert "warning=mismatched_lengths" in captured.out
