"""Tests for equities/data/mantle_signal.py."""
from __future__ import annotations

import socket
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import pytest

from equities.data.mantle_signal import MantleSignal, fetch_mantle_signal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _connection_error(*args, **kwargs):
    raise urllib.error.URLError(socket.gaierror("Name or service not known"))


def _timeout_error(*args, **kwargs):
    raise TimeoutError("timed out")


# ---------------------------------------------------------------------------
# Core contract: never raises, always returns MantleSignal
# ---------------------------------------------------------------------------

class TestNeverRaises:
    def test_returns_mantle_signal_when_both_fetches_fail_url_error(self):
        with patch("urllib.request.urlopen", side_effect=_connection_error):
            result = fetch_mantle_signal(timeout=1.0)
        assert isinstance(result, MantleSignal)

    def test_returns_mantle_signal_when_both_fetches_fail_timeout(self):
        with patch("urllib.request.urlopen", side_effect=_timeout_error):
            result = fetch_mantle_signal(timeout=1.0)
        assert isinstance(result, MantleSignal)

    def test_returns_mantle_signal_when_both_fetches_fail_http_error(self):
        http_err = urllib.error.HTTPError(
            url="http://x", code=503, msg="Service Unavailable",
            hdrs=MagicMock(), fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            result = fetch_mantle_signal(timeout=1.0)
        assert isinstance(result, MantleSignal)


# ---------------------------------------------------------------------------
# Error field behaviour
# ---------------------------------------------------------------------------

class TestErrorField:
    def test_error_set_when_both_fail(self):
        with patch("urllib.request.urlopen", side_effect=_connection_error):
            result = fetch_mantle_signal(timeout=1.0)
        assert result.error is not None
        assert len(result.error) > 0

    def test_error_is_none_when_both_succeed(self):
        """Simulate both APIs returning valid data — error should be None."""
        import json

        meth_payload = json.dumps({"apr": "4.2"}).encode()
        gas_payload = json.dumps({"jsonrpc": "2.0", "result": "0x3B9ACA00", "id": 1}).encode()

        call_count = 0

        class FakeResponse:
            def __init__(self, data):
                self._data = data

            def read(self):
                return self._data

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def fake_urlopen(req, timeout):
            nonlocal call_count
            call_count += 1
            # First call(s) = mETH endpoints; last call = RPC
            if "rpc.mantle.xyz" in req.full_url:
                return FakeResponse(gas_payload)
            return FakeResponse(meth_payload)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = fetch_mantle_signal(timeout=1.0)

        assert result.error is None
        assert result.meth_apy == pytest.approx(0.042)
        assert result.gas_price_gwei == pytest.approx(1.0)  # 0x3B9ACA00 = 1e9 wei = 1 Gwei

    def test_partial_error_when_only_one_fails(self):
        """mETH fails, RPC succeeds — error mentions mETH but gas is populated."""
        import json

        gas_payload = json.dumps({"jsonrpc": "2.0", "result": "0x77359400", "id": 1}).encode()

        class FakeResponse:
            def __init__(self, data):
                self._data = data

            def read(self):
                return self._data

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def fake_urlopen(req, timeout):
            if "rpc.mantle.xyz" in req.full_url:
                return FakeResponse(gas_payload)
            raise urllib.error.URLError("connection refused")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = fetch_mantle_signal(timeout=1.0)

        assert result.error is not None
        assert result.gas_price_gwei is not None
        assert result.meth_apy is None


# ---------------------------------------------------------------------------
# Source field always populated
# ---------------------------------------------------------------------------

class TestSourceField:
    def test_source_always_set_on_success(self):
        import json

        meth_payload = json.dumps({"apy": 0.038}).encode()
        gas_payload = json.dumps({"jsonrpc": "2.0", "result": "0x1DCD6500", "id": 1}).encode()

        class FakeResponse:
            def __init__(self, data):
                self._data = data

            def read(self):
                return self._data

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def fake_urlopen(req, timeout):
            if "rpc.mantle.xyz" in req.full_url:
                return FakeResponse(gas_payload)
            return FakeResponse(meth_payload)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = fetch_mantle_signal(timeout=1.0)

        assert result.source
        assert "mantle" in result.source.lower()

    def test_source_always_set_on_failure(self):
        with patch("urllib.request.urlopen", side_effect=_connection_error):
            result = fetch_mantle_signal(timeout=1.0)
        assert result.source
        assert "mantle" in result.source.lower()


# ---------------------------------------------------------------------------
# APY normalisation
# ---------------------------------------------------------------------------

class TestApyNormalisation:
    """Values > 1.0 should be divided by 100 to normalise to a ratio."""

    def _run_with_apy(self, raw_value) -> MantleSignal:
        import json

        payload = json.dumps({"apr": raw_value}).encode()

        class FakeResponse:
            def read(self):
                return payload

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def fake_urlopen(req, timeout):
            if "rpc.mantle.xyz" in req.full_url:
                raise urllib.error.URLError("skip")
            return FakeResponse()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            return fetch_mantle_signal(timeout=1.0)

    def test_percentage_normalised_to_ratio(self):
        result = self._run_with_apy("3.75")
        assert result.meth_apy == pytest.approx(0.0375)

    def test_ratio_passed_through_unchanged(self):
        result = self._run_with_apy("0.0375")
        assert result.meth_apy == pytest.approx(0.0375)


# ---------------------------------------------------------------------------
# fetched_at field
# ---------------------------------------------------------------------------

class TestFetchedAt:
    def test_fetched_at_is_iso_timestamp(self):
        from datetime import datetime

        with patch("urllib.request.urlopen", side_effect=_connection_error):
            result = fetch_mantle_signal(timeout=1.0)

        # Should parse without error
        dt = datetime.fromisoformat(result.fetched_at)
        assert dt.tzinfo is not None  # timezone-aware
