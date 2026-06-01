import json
from pathlib import Path
from datetime import datetime, timezone

from strategies.crypto_updown.spot import parse_trade, SpotTick

FIXTURE = json.loads((Path(__file__).parent / "fixtures/binance_trade.json").read_text())


def test_parse_trade_returns_spot_tick():
    tick = parse_trade(FIXTURE)
    assert isinstance(tick, SpotTick)


def test_parse_trade_price():
    tick = parse_trade(FIXTURE)
    assert tick.price == 67432.15


def test_parse_trade_symbol():
    tick = parse_trade(FIXTURE)
    assert tick.symbol == "BTCUSDT"


def test_parse_trade_timestamp_is_utc():
    tick = parse_trade(FIXTURE)
    assert tick.ts.tzinfo is not None
    assert tick.ts.tzinfo == timezone.utc


def test_parse_trade_timestamp_value():
    tick = parse_trade(FIXTURE)
    # T field = 1748764800123 ms → epoch seconds
    expected_s = 1748764800.123
    assert abs(tick.ts.timestamp() - expected_s) < 0.01


def test_parse_trade_rejects_non_trade_event():
    import pytest
    msg = dict(FIXTURE)
    msg["e"] = "bookTicker"
    with pytest.raises(ValueError):
        parse_trade(msg)
