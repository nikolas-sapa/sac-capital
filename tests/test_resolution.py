"""Tests for core/resolution.py — TDD step 1 (written before implementation).

Covers:
- parse_resolution on a resolved fixture (closed=True, outcomePrices settled)
- parse_resolution on the open fixture (closed=False) returns None
- resolve_open_positions: integrates Ledger + async fetch_fn
- Dedupe: fetch_fn called once per condition_id even with multiple positions
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# ---------------------------------------------------------------------------
# Fixtures paths
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures"
RESOLVED_FIXTURE = FIXTURES / "gamma_resolved_market.json"
OPEN_FIXTURE = FIXTURES / "gamma_market.json"


def _load_fixture(path: Path) -> dict:
    """Load the first item from a gamma JSON array fixture."""
    data = json.loads(path.read_text())
    return data[0]


# ---------------------------------------------------------------------------
# Helpers for building a real Ledger with fills
# ---------------------------------------------------------------------------

from datetime import datetime, timezone

from core.execution.base import Fill
from core.ledger import Ledger
from core.markets import Market, Outcome
from core.strategy import Signal


def _market(condition_id: str, tok_yes: str = "tok-yes", tok_no: str = "tok-no") -> Market:
    return Market(
        condition_id=condition_id,
        question="Will X happen?",
        outcomes=[
            Outcome(token_id=tok_yes, label="Yes", best_bid=0.55, best_ask=0.56),
            Outcome(token_id=tok_no, label="No", best_bid=0.43, best_ask=0.44),
        ],
        end_date=datetime(2026, 12, 31, tzinfo=timezone.utc),
        closed=False,
    )


def _fill(market: Market, tok: str = "tok-yes", stake: float = 10.0) -> Fill:
    return Fill(
        signal=Signal(
            market=market,
            token_id=tok,
            fair_prob=0.65,
            price=0.56,
            confidence=0.8,
            reason="test",
        ),
        stake=stake,
        shares=17.86,
        avg_price=0.56,
        timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        mode="paper",
    )


# ===========================================================================
# Tests for parse_resolution
# ===========================================================================

class TestParseResolution:
    def test_closed_market_returns_winning_clob_id(self):
        """parse_resolution on the CLOSED/settled fixture returns the Yes clobTokenId.

        Fixture has outcomePrices=["1","0"] so index 0 (Yes) wins.
        The expected result is the first clobTokenId from the fixture.
        """
        from core.resolution import parse_resolution

        item = _load_fixture(RESOLVED_FIXTURE)
        result = parse_resolution(item)

        # clobTokenIds[0] is the Yes outcome (outcomePrices[0] == "1")
        clob_ids = json.loads(item["clobTokenIds"])
        assert result == clob_ids[0]

    def test_open_market_returns_none(self):
        """parse_resolution on the OPEN fixture (closed=False) returns None."""
        from core.resolution import parse_resolution

        item = _load_fixture(OPEN_FIXTURE)
        result = parse_resolution(item)

        assert result is None

    def test_no_price_near_1_returns_none(self):
        """parse_resolution returns None when no outcome price is >= 0.99."""
        from core.resolution import parse_resolution

        item = {
            "closed": True,
            "outcomePrices": '["0.53", "0.47"]',
            "clobTokenIds": '["clob-a", "clob-b"]',
        }
        assert parse_resolution(item) is None

    def test_near_1_price_accepted_as_winning(self):
        """parse_resolution accepts a price >= 0.99 as winning (not just exactly 1.0)."""
        from core.resolution import parse_resolution

        item = {
            "closed": True,
            "outcomePrices": '["0.0000001", "0.9999999"]',
            "clobTokenIds": '["clob-a", "clob-b"]',
        }
        assert parse_resolution(item) == "clob-b"


# ===========================================================================
# Tests for resolve_open_positions
# ===========================================================================

class TestResolveOpenPositions:
    @pytest.mark.asyncio
    async def test_settled_condition_cleared_other_stays_open(self, tmp_path):
        """fetch_fn returns a winning id for condition A, None for B.

        After resolve_open_positions:
        - A's rows are settled (no longer in open_positions)
        - B's rows remain open
        - returned count == number of rows for A
        """
        from core.resolution import resolve_open_positions

        db_path = tmp_path / "ledger.db"
        ledger = Ledger(db_path)

        market_a = _market("cond-A", "clob-yes-a", "clob-no-a")
        market_b = _market("cond-B", "clob-yes-b", "clob-no-b")

        # Two fills on condition A, one on condition B
        ledger.record(_fill(market_a, "clob-yes-a", stake=10.0))
        ledger.record(_fill(market_a, "clob-no-a", stake=5.0))
        ledger.record(_fill(market_b, "clob-yes-b", stake=7.0))

        async def fetch_fn(condition_id: str) -> str | None:
            if condition_id == "cond-A":
                return "clob-yes-a"
            return None

        count = await resolve_open_positions(ledger, fetch_fn)

        # Two rows on cond-A settled
        assert count == 2
        # cond-B still open
        open_pos = ledger.open_positions()
        assert len(open_pos) == 1
        assert open_pos[0]["condition_id"] == "cond-B"

    @pytest.mark.asyncio
    async def test_all_none_fetch_returns_zero(self, tmp_path):
        """If fetch_fn returns None for all conditions, nothing is settled."""
        from core.resolution import resolve_open_positions

        db_path = tmp_path / "ledger.db"
        ledger = Ledger(db_path)
        market = _market("cond-X")
        ledger.record(_fill(market))

        async def fetch_fn(condition_id: str) -> str | None:
            return None

        count = await resolve_open_positions(ledger, fetch_fn)
        assert count == 0
        assert len(ledger.open_positions()) == 1

    @pytest.mark.asyncio
    async def test_fetch_fn_called_once_per_condition(self, tmp_path):
        """fetch_fn is awaited exactly once per distinct condition_id (dedupe)."""
        from core.resolution import resolve_open_positions

        db_path = tmp_path / "ledger.db"
        ledger = Ledger(db_path)
        market = _market("cond-SAME")

        # Two fills on the SAME condition
        ledger.record(_fill(market, "tok-yes"))
        ledger.record(_fill(market, "tok-yes"))

        mock_fn = AsyncMock(return_value=None)

        await resolve_open_positions(ledger, mock_fn)

        # fetch_fn called exactly once, not twice
        mock_fn.assert_awaited_once_with("cond-SAME")

    @pytest.mark.asyncio
    async def test_empty_ledger_zero_count(self, tmp_path):
        """resolve_open_positions on an empty ledger returns 0 without calling fetch_fn."""
        from core.resolution import resolve_open_positions

        db_path = tmp_path / "ledger.db"
        ledger = Ledger(db_path)

        mock_fn = AsyncMock(return_value=None)
        count = await resolve_open_positions(ledger, mock_fn)

        assert count == 0
        mock_fn.assert_not_awaited()
