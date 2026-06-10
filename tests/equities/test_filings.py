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

    def fake_get(url, headers=None, timeout=None):  # noqa: ANN001
        calls.append(url)
        if url.endswith("CIK0000320193.json"):
            return _Response(
                {
                    "filings": {
                        "recent": {
                            "form": ["8-K", "10-Q"],
                            "filingDate": ["2026-06-08", "2026-05-01"],
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
