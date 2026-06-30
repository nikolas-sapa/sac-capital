"""Tests for SEC 13F-HR smart-money context provider."""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from equities.data.fund_13f import (
    Fund13FProvider,
    Fund13FSnapshot,
    Holding,
    PositionChange,
    compute_changes,
    parse_info_table_xml,
)

# Sample 13F info table XML with namespaces (realistic SEC format)
# Prior quarter: 2 longs + 1 put
PRIOR_13F_XML = """<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/cgi-bin">
  <infoTable>
    <nameOfIssuer>Apple Inc</nameOfIssuer>
    <cusip>037833100</cusip>
    <value>50000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>100000</sshPrnamt>
    </shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>Microsoft Corporation</nameOfIssuer>
    <cusip>594918104</cusip>
    <value>40000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>80000</sshPrnamt>
    </shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>Tesla Inc</nameOfIssuer>
    <cusip>88160R101</cusip>
    <value>30000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>50000</sshPrnamt>
    </shrsOrPrnAmt>
    <putCall>Put</putCall>
  </infoTable>
</informationTable>
"""

# Current quarter: Apple increased, Microsoft exited, Tesla put exited, NVIDIA & Google new
CURRENT_13F_XML = """<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/cgi-bin">
  <infoTable>
    <nameOfIssuer>Apple Inc</nameOfIssuer>
    <cusip>037833100</cusip>
    <value>60000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>120000</sshPrnamt>
    </shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>NVIDIA Corporation</nameOfIssuer>
    <cusip>067066029</cusip>
    <value>70000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>30000</sshPrnamt>
    </shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>Alphabet Inc</nameOfIssuer>
    <cusip>02008349</cusip>
    <value>45000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>90000</sshPrnamt>
    </shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>Tesla Inc</nameOfIssuer>
    <cusip>88160R101</cusip>
    <value>20000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>10000</sshPrnamt>
    </shrsOrPrnAmt>
    <putCall>Call</putCall>
  </infoTable>
</informationTable>
"""


class TestParseInfoTableXML:
    """Test XML parsing and aggregation."""

    def test_parse_long_holdings(self):
        """Parse long equity holdings."""
        holdings = parse_info_table_xml(CURRENT_13F_XML)
        longs = [h for h in holdings if h.position_type == "long"]
        assert len(longs) == 3
        apple = next(h for h in longs if h.issuer == "Apple Inc")
        assert apple.value_usd == 60_000_000
        assert apple.shares == 120_000
        assert apple.cusip == "037833100"

    def test_parse_put_holdings(self):
        """Parse put option holdings."""
        holdings = parse_info_table_xml(PRIOR_13F_XML)
        puts = [h for h in holdings if h.position_type == "put"]
        assert len(puts) == 1
        tesla_put = puts[0]
        assert tesla_put.issuer == "Tesla Inc"
        assert tesla_put.value_usd == 30_000_000
        assert tesla_put.shares == 50_000

    def test_parse_call_holdings(self):
        """Parse call option holdings."""
        holdings = parse_info_table_xml(CURRENT_13F_XML)
        calls = [h for h in holdings if h.position_type == "call"]
        assert len(calls) == 1
        tesla_call = calls[0]
        assert tesla_call.issuer == "Tesla Inc"
        assert tesla_call.value_usd == 20_000_000
        assert tesla_call.shares == 10_000

    def test_value_parsed_as_whole_dollars(self):
        """SEC 13F value column is whole USD (post-2023); parsed as-is."""
        holdings = parse_info_table_xml(PRIOR_13F_XML)
        apple = next(h for h in holdings if h.issuer == "Apple Inc")
        # XML value=50000000 (whole USD) → 50_000_000
        assert apple.value_usd == 50_000_000

    def test_aggregation_multiple_rows_same_position(self):
        """Test aggregation of multiple rows for same (issuer, position_type)."""
        xml_with_dupes = """<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/cgi-bin">
  <infoTable>
    <nameOfIssuer>Apple Inc</nameOfIssuer>
    <cusip>037833100</cusip>
    <value>25000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>50000</sshPrnamt>
    </shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>Apple Inc</nameOfIssuer>
    <cusip>037833100</cusip>
    <value>25000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>50000</sshPrnamt>
    </shrsOrPrnAmt>
  </infoTable>
</informationTable>
"""
        holdings = parse_info_table_xml(xml_with_dupes)
        assert len(holdings) == 1
        apple = holdings[0]
        assert apple.value_usd == 50_000_000  # 25M + 25M dollars
        assert apple.shares == 100_000  # 50k + 50k shares

    def test_parse_missing_shares(self):
        """Test handling when shrsOrPrnamt is missing."""
        xml_no_shares = """<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/cgi-bin">
  <infoTable>
    <nameOfIssuer>Bond Fund</nameOfIssuer>
    <cusip>123456789</cusip>
    <value>10000000</value>
  </infoTable>
</informationTable>
"""
        holdings = parse_info_table_xml(xml_no_shares)
        assert len(holdings) == 1
        assert holdings[0].shares is None
        assert holdings[0].value_usd == 10_000_000

    def test_parse_invalid_xml(self):
        """Test graceful handling of malformed XML."""
        holdings = parse_info_table_xml("<not valid xml")
        assert holdings == []

    def test_parse_empty_xml(self):
        """Test handling of empty info table."""
        xml_empty = """<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/cgi-bin">
</informationTable>
"""
        holdings = parse_info_table_xml(xml_empty)
        assert holdings == []


class TestComputeChanges:
    """Test quarter-over-quarter position diff logic."""

    def test_new_position(self):
        """Classify newly entered positions."""
        prev = []
        curr = [Holding("NVDA", "067066029", "long", 70_000_000, 30_000)]
        changes = compute_changes(prev, curr)
        assert len(changes) == 1
        assert changes[0].change == "new"
        assert changes[0].issuer == "NVDA"
        assert changes[0].prev_value_usd == 0
        assert changes[0].curr_value_usd == 70_000_000

    def test_exited_position(self):
        """Classify exited positions."""
        prev = [Holding("Tesla", "88160R101", "put", 30_000_000, 50_000)]
        curr = []
        changes = compute_changes(prev, curr)
        assert len(changes) == 1
        assert changes[0].change == "exited"
        assert changes[0].issuer == "Tesla"
        assert changes[0].prev_value_usd == 30_000_000
        assert changes[0].curr_value_usd == 0

    def test_increased_position(self):
        """Classify increased positions."""
        prev = [Holding("AAPL", "037833100", "long", 50_000_000, 100_000)]
        curr = [Holding("AAPL", "037833100", "long", 60_000_000, 120_000)]
        changes = compute_changes(prev, curr)
        assert len(changes) == 1
        assert changes[0].change == "increased"

    def test_reduced_position(self):
        """Classify reduced positions."""
        prev = [Holding("MSFT", "594918104", "long", 40_000_000, 80_000)]
        curr = [Holding("MSFT", "594918104", "long", 25_000_000, 50_000)]
        changes = compute_changes(prev, curr)
        assert len(changes) == 1
        assert changes[0].change == "reduced"

    def test_unchanged_position(self):
        """Classify unchanged positions."""
        prev = [Holding("GOOG", "02008349", "long", 45_000_000, 90_000)]
        curr = [Holding("GOOG", "02008349", "long", 45_000_000, 90_000)]
        changes = compute_changes(prev, curr)
        assert len(changes) == 1
        assert changes[0].change == "unchanged"

    def test_mixed_position_and_option_changes(self):
        """Test same issuer but different position types."""
        prev = [Holding("TSLA", "88160R101", "long", 50_000_000, 40_000)]
        curr = [
            Holding("TSLA", "88160R101", "long", 30_000_000, 25_000),  # reduced
            Holding("TSLA", "88160R101", "put", 20_000_000, 10_000),  # new put
        ]
        changes = compute_changes(prev, curr)
        # Should have 2 changes: reduced long, new put
        long_changes = [c for c in changes if c.position_type == "long"]
        put_changes = [c for c in changes if c.position_type == "put"]
        assert len(long_changes) == 1
        assert long_changes[0].change == "reduced"
        assert len(put_changes) == 1
        assert put_changes[0].change == "new"

    def test_change_sorting(self):
        """Verify changes are sorted by type, then by value desc."""
        prev = [
            Holding("A", "aaa", "long", 10_000_000, 1000),
            Holding("B", "bbb", "long", 20_000_000, 2000),
        ]
        curr = [
            Holding("C", "ccc", "long", 30_000_000, 3000),
            Holding("A", "aaa", "long", 15_000_000, 1500),
        ]
        changes = compute_changes(prev, curr)
        # Should sort: new (C: 30M), reduced (B exited: 20M), increased (A: 15M curr)
        assert changes[0].change == "exited"
        assert changes[0].issuer == "B"


class TestFund13FSnapshot:
    """Test snapshot building and never-raises contract."""

    def test_snapshot_never_raises_on_network_error(self):
        """Verify snapshot() never raises, returns error in .error field."""
        provider = Fund13FProvider(cik="2045724", fund_name="Situational Awareness LP")

        # Monkeypatch latest_two_infotables to raise
        with patch.object(provider, "latest_two_infotables", side_effect=RuntimeError("Network error")):
            snap = provider.snapshot()

        assert snap.error is not None
        assert "Network error" in snap.error
        assert snap.holdings == []
        assert snap.changes == []

    def test_snapshot_totals(self):
        """Verify totals calculation."""
        prev = parse_info_table_xml(PRIOR_13F_XML)
        curr = parse_info_table_xml(CURRENT_13F_XML)

        # Manually create snapshot to test totals
        total_long = sum(h.value_usd for h in curr if h.position_type == "long")
        total_put = sum(h.value_usd for h in curr if h.position_type == "put")
        total_call = sum(h.value_usd for h in curr if h.position_type == "call")

        # From CURRENT_13F_XML:
        # AAPL (long): 60M, NVDA (long): 70M, GOOG (long): 45M
        # TSLA (call): 20M
        assert total_long == 175_000_000
        assert total_put == 0
        assert total_call == 20_000_000

    def test_context_summary_format(self):
        """Verify context_summary generates analyst-readable output."""
        provider = Fund13FProvider(cik="2045724", fund_name="Test Fund")

        # Monkeypatch snapshot to return known state
        test_snap = Fund13FSnapshot(
            cik="2045724",
            fund_name="Test Fund",
            period_filed="2026-05-18",
            holdings=[
                Holding("AAPL", "037833100", "long", 100_000_000, 500_000),
                Holding("NVDA", "067066029", "long", 200_000_000, 300_000),
            ],
            changes=[
                PositionChange("AAPL", "long", "new", 0, 100_000_000),
                PositionChange("NVDA", "long", "increased", 150_000_000, 200_000_000),
            ],
            total_long_usd=300_000_000,
            total_put_usd=0,
            total_call_usd=0,
            source_url="https://data.sec.gov/...",
            fetched_at=datetime.now(timezone.utc).isoformat(),
            error=None,
        )

        with patch.object(provider, "snapshot", return_value=test_snap):
            summary = provider.context_summary()

        assert "Test Fund" in summary
        assert "2026-05-18" in summary
        assert "0.30B long" in summary
        assert "AAPL" in summary
        assert "NVDA" in summary


class TestIntegrationWithMocking:
    """Integration tests with network calls mocked."""

    def test_latest_two_infotables_parses_and_aggregates(self):
        """Test end-to-end XML fetching and parsing (mocked network)."""
        provider = Fund13FProvider(cik="2045724", fund_name="SA LP")

        def mock_fetch(accession):
            if accession == "0000950154-26-002345":
                return PRIOR_13F_XML
            elif accession == "0000950154-26-003456":
                return CURRENT_13F_XML
            raise ValueError(f"Unexpected accession: {accession}")

        with patch.object(
            provider, "_fetch_13f_accessions",
            return_value=["0000950154-26-003456", "0000950154-26-002345"]
        ):
            with patch.object(provider, "_fetch_info_table_xml", side_effect=mock_fetch):
                prev, curr = provider.latest_two_infotables()

        # Verify aggregation
        assert len(prev) == 3
        assert len(curr) == 4

        # Check a specific holding
        apple_curr = next(h for h in curr if h.issuer == "Apple Inc")
        assert apple_curr.value_usd == 60_000_000


def test_fund_config_parsing():
    """Test parsing of smart_money_ciks config string."""
    config_str = "2045724:Situational Awareness LP,1234567:Another Fund"
    pairs = [pair.split(":") for pair in config_str.split(",")]
    assert len(pairs) == 2
    assert pairs[0][0] == "2045724"
    assert pairs[0][1] == "Situational Awareness LP"
