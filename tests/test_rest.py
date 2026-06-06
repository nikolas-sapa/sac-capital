"""Tests for core.clob.rest.parse_market — NO network, fixture-only."""
import json
from datetime import timezone
from pathlib import Path

import pytest

from core.clob.rest import fetch_markets, parse_market

FIXTURE = Path(__file__).parent / "fixtures" / "gamma_market.json"


@pytest.fixture()
def raw_market() -> dict:
    data = json.loads(FIXTURE.read_text())
    return data[0]


def test_parse_market_condition_id(raw_market):
    market = parse_market(raw_market)
    assert market.condition_id == "0x1fad72fae204143ff1c3035e99e7c0f65ea8d5cd9bd1070987bd1a3316f772be"


def test_parse_market_question(raw_market):
    market = parse_market(raw_market)
    assert market.question == "New Rihanna Album before GTA VI?"


def test_parse_market_closed(raw_market):
    market = parse_market(raw_market)
    assert market.closed is False


def test_parse_market_end_date_timezone_aware_utc(raw_market):
    market = parse_market(raw_market)
    assert market.end_date.tzinfo is not None
    assert market.end_date.tzinfo == timezone.utc
    assert market.end_date.year == 2026
    assert market.end_date.month == 7
    assert market.end_date.day == 31


def test_parse_market_outcomes_non_empty(raw_market):
    market = parse_market(raw_market)
    assert len(market.outcomes) > 0


def test_parse_market_outcomes_labels(raw_market):
    market = parse_market(raw_market)
    labels = [o.label for o in market.outcomes]
    assert labels == ["Yes", "No"]


def test_parse_market_outcomes_token_ids(raw_market):
    market = parse_market(raw_market)
    token_ids = [o.token_id for o in market.outcomes]
    assert token_ids[0] == "98022490269692409998126496127597032490334070080325855126491859374983463996227"
    assert token_ids[1] == "53831553061883006530739877284105938919721408776239639687877978808906551086026"


def test_parse_market_outcomes_prices(raw_market):
    market = parse_market(raw_market)
    # outcomePrices used as mid-price fallback for best_bid and best_ask
    yes = market.outcomes[0]
    no = market.outcomes[1]
    assert yes.best_bid == pytest.approx(0.53)
    assert yes.best_ask == pytest.approx(0.53)
    assert no.best_bid == pytest.approx(0.47)
    assert no.best_ask == pytest.approx(0.47)


@pytest.mark.asyncio
async def test_fetch_markets_skips_items_missing_end_date(monkeypatch, raw_market):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            bad = dict(raw_market)
            bad.pop("endDate", None)
            return [bad, raw_market]

    class FakeClient:
        def __init__(self, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, params):
            return FakeResponse()

    monkeypatch.setattr("core.clob.rest.httpx.AsyncClient", FakeClient)
    markets = await fetch_markets(limit=2)
    assert len(markets) == 1
    assert markets[0].condition_id == raw_market["conditionId"]
