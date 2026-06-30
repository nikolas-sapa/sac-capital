"""Tests for House Clerk financial disclosure provider."""
from datetime import date

import pytest

from equities.data.house_clerk_disclosures import parse_ptr_text


PELOSI_PTR_SAMPLE = """
PERIODIC TRANSACTION REPORT

REPRESENTATIVE: Nancy Pelosi
STATE: CA11
FILING DATE: 06/26/2026

CONFIDENTIAL

Transactions:

SP Intel Corporation - Common Stock
(INTC) [OP]
P 05/29/202605/29/2026$1,000,001 -
$5,000,000

SP Uber Technologies Inc - Common Stock
(UBER) [OP]
P 05/20/202605/29/2026$500,001 -
$1,000,000

Some Bond Transaction - No Ticker
(--) [OB]
P 05/15/202605/29/2026$100,001 -
$500,000

JT Apple Inc - Common Stock
(AAPL) [OP]
S 05/10/202605/29/2026$50,001 -
$100,000

End of Report
"""


def test_parse_ptr_text_intc_buy():
    """Parse INTC buy transaction with spouse owner."""
    trades = parse_ptr_text(
        PELOSI_PTR_SAMPLE,
        filed_date="06/26/2026",
        politician="Nancy Pelosi",
        office="CA11",
        source_url="https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20034836.pdf",
    )

    intc = next((t for t in trades if t.ticker == "INTC"), None)
    assert intc is not None
    assert intc.ticker == "INTC"
    assert intc.owner == "spouse"
    assert intc.transaction_type == "buy"
    assert intc.amount_min == 1_000_001
    assert intc.amount_max == 5_000_000
    assert intc.transaction_date == date(2026, 5, 29)
    assert intc.date_filed == date(2026, 6, 26)
    assert intc.politician == "Nancy Pelosi"
    assert intc.chamber == "house"


def test_parse_ptr_text_uber_buy():
    """Parse UBER buy transaction."""
    trades = parse_ptr_text(
        PELOSI_PTR_SAMPLE,
        filed_date="06/26/2026",
        politician="Nancy Pelosi",
        office="CA11",
        source_url="https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20034836.pdf",
    )

    uber = next((t for t in trades if t.ticker == "UBER"), None)
    assert uber is not None
    assert uber.ticker == "UBER"
    assert uber.owner == "spouse"
    assert uber.transaction_type == "buy"
    assert uber.amount_min == 500_001
    assert uber.amount_max == 1_000_000


def test_parse_ptr_text_aapl_sell_joint():
    """Parse AAPL sell transaction with joint owner."""
    trades = parse_ptr_text(
        PELOSI_PTR_SAMPLE,
        filed_date="06/26/2026",
        politician="Nancy Pelosi",
        office="CA11",
        source_url="https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20034836.pdf",
    )

    aapl = next((t for t in trades if t.ticker == "AAPL"), None)
    assert aapl is not None
    assert aapl.ticker == "AAPL"
    assert aapl.owner == "joint"
    assert aapl.transaction_type == "sell"
    assert aapl.amount_min == 50_001
    assert aapl.amount_max == 100_000
    assert aapl.transaction_date == date(2026, 5, 10)


def test_parse_ptr_text_skip_no_ticker():
    """Skip transactions with no parseable ticker."""
    trades = parse_ptr_text(
        PELOSI_PTR_SAMPLE,
        filed_date="06/26/2026",
        politician="Nancy Pelosi",
        office="CA11",
        source_url="https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20034836.pdf",
    )

    # Should have INTC, UBER, AAPL but NOT the bond (-- ticker)
    tickers = [t.ticker for t in trades]
    assert "INTC" in tickers
    assert "UBER" in tickers
    assert "AAPL" in tickers
    assert "--" not in tickers
    assert len(tickers) == 3


def test_parse_ptr_text_empty_text():
    """Empty text yields no trades."""
    trades = parse_ptr_text(
        "",
        filed_date="06/26/2026",
        politician="Test Person",
        office="TX1",
        source_url="http://example.com",
    )
    assert trades == []


def test_parse_ptr_text_invalid_filed_date():
    """Invalid filed_date yields no trades."""
    trades = parse_ptr_text(
        PELOSI_PTR_SAMPLE,
        filed_date="not-a-date",
        politician="Test Person",
        office="TX1",
        source_url="http://example.com",
    )
    assert trades == []


def test_parse_ptr_text_filed_date_as_date_object():
    """filed_date can be a date object."""
    trades = parse_ptr_text(
        PELOSI_PTR_SAMPLE,
        filed_date=date(2026, 6, 26),
        politician="Nancy Pelosi",
        office="CA11",
        source_url="https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20034836.pdf",
    )

    assert len(trades) == 3
    assert all(t.date_filed == date(2026, 6, 26) for t in trades)


def test_parse_ptr_text_dc_owner_mapped():
    """DC (dependent child) owner code is mapped correctly."""
    text = """
DC Microsoft Corporation - Common Stock
(MSFT) [OP]
P 05/25/202605/29/2026$2,000,001 -
$5,000,000
"""
    trades = parse_ptr_text(
        text,
        filed_date="06/29/2026",
        politician="Rep Test",
        office="NY1",
        source_url="http://example.com",
    )

    assert len(trades) == 1
    assert trades[0].ticker == "MSFT"
    assert trades[0].owner == "dependent_child"


def test_parse_ptr_text_self_owner_by_default():
    """No owner code defaults to 'self'."""
    text = """
Google LLC - Common Stock
(GOOGL) [OP]
P 05/15/202605/29/2026$3,000,001 -
$4,000,000
"""
    trades = parse_ptr_text(
        text,
        filed_date="06/29/2026",
        politician="Rep Test",
        office="TX1",
        source_url="http://example.com",
    )

    assert len(trades) == 1
    assert trades[0].owner == "self"


@pytest.mark.parametrize("type_code,expected_type", [
    ("P", "buy"),
    ("S", "sell"),
    ("E", "exchange"),
])
def test_parse_ptr_text_transaction_types(type_code, expected_type):
    """Parse various transaction type codes."""
    text = f"""
Tesla Inc - Common Stock
(TSLA) [OP]
{type_code} 05/15/202605/29/2026$100,001 -
$500,000
"""
    trades = parse_ptr_text(
        text,
        filed_date="06/29/2026",
        politician="Rep Test",
        office="TX1",
        source_url="http://example.com",
    )

    assert len(trades) == 1
    assert trades[0].transaction_type == expected_type
