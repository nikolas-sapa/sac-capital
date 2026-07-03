"""Point-in-time look-ahead guard tests."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from equities.pit import LookAheadError, assert_point_in_time


class TestLookAheadGuard:
    """Test suite for PIT cutoff guards."""

    def test_future_raises_error(self):
        """Future data should raise LookAheadError."""
        cutoff = "2026-07-03T00:00:00Z"
        sources = [{"name": "senate", "as_of_utc": "2026-07-04T00:00:00Z"}]
        with pytest.raises(LookAheadError):
            assert_point_in_time(cutoff, sources)

    def test_past_passes(self):
        """Past data should pass silently."""
        cutoff = "2026-07-03T12:00:00Z"
        sources = [{"name": "senate", "as_of_utc": "2026-07-03T11:59:59Z"}]
        warnings = assert_point_in_time(cutoff, sources)
        assert warnings == []

    def test_equal_passes(self):
        """Equal timestamp should pass (not exceed cutoff)."""
        cutoff = "2026-07-03T12:00:00Z"
        sources = [{"name": "senate", "as_of_utc": "2026-07-03T12:00:00Z"}]
        warnings = assert_point_in_time(cutoff, sources)
        assert warnings == []

    def test_none_returns_warning(self):
        """Sources with as_of_utc=None should return a warning."""
        cutoff = "2026-07-03T12:00:00Z"
        sources = [{"name": "senate", "as_of_utc": None}]
        warnings = assert_point_in_time(cutoff, sources)
        assert warnings == ["senate"]

    def test_missing_key_returns_warning(self):
        """Sources without as_of_utc key should return a warning."""
        cutoff = "2026-07-03T12:00:00Z"
        sources = [{"name": "news"}]
        warnings = assert_point_in_time(cutoff, sources)
        assert warnings == ["news"]

    def test_z_suffix(self):
        """Z suffix in ISO-8601 should be handled."""
        cutoff = "2026-07-03T12:00:00Z"
        sources = [{"name": "senate", "as_of_utc": "2026-07-03T11:59:59Z"}]
        warnings = assert_point_in_time(cutoff, sources)
        assert warnings == []

    def test_mixed_valid_invalid(self):
        """Multiple sources with mixed valid/invalid timestamps."""
        cutoff = "2026-07-03T12:00:00Z"
        sources = [
            {"name": "senate", "as_of_utc": "2026-07-03T11:59:59Z"},
            {"name": "news", "as_of_utc": None},
            {"name": "filing", "as_of_utc": "2026-07-03T12:00:00Z"},
            {"name": "macro"},
        ]
        warnings = assert_point_in_time(cutoff, sources)
        assert set(warnings) == {"news", "macro"}

    def test_one_future_fails(self):
        """Single future source in batch should fail."""
        cutoff = "2026-07-03T12:00:00Z"
        sources = [
            {"name": "senate", "as_of_utc": "2026-07-03T11:59:59Z"},
            {"name": "future", "as_of_utc": "2026-07-03T12:00:01Z"},
        ]
        with pytest.raises(LookAheadError) as exc_info:
            assert_point_in_time(cutoff, sources)
        assert "future" in str(exc_info.value)

    def test_iso_formats(self):
        """Test various ISO-8601 formats."""
        cutoff = "2026-07-03T12:00:00+00:00"
        sources_z = [{"name": "test", "as_of_utc": "2026-07-03T12:00:00Z"}]
        assert assert_point_in_time(cutoff, sources_z) == []

        sources_plus = [{"name": "test", "as_of_utc": "2026-07-03T12:00:00+00:00"}]
        assert assert_point_in_time(cutoff, sources_plus) == []

    def test_empty_sources(self):
        """Empty sources list should return empty warnings."""
        cutoff = "2026-07-03T12:00:00Z"
        warnings = assert_point_in_time(cutoff, [])
        assert warnings == []
