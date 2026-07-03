"""Tests for explicit broker status mapping in runner_equities."""

from runner_equities import _local_status_for


def test_known_statuses():
    """Test mapping of known broker statuses to local statuses."""
    assert _local_status_for("filled") == "open"
    assert _local_status_for("partially_filled") == "partially_filled"
    assert _local_status_for("new") == "submitted"
    assert _local_status_for("accepted") == "submitted"


def test_terminal_failures_map_to_rejected():
    """Test that all terminal failure statuses map to 'rejected'."""
    for s in ("rejected", "canceled", "cancelled", "expired", "suspended", "stopped"):
        assert _local_status_for(s) == "rejected"


def test_unknown_status_maps_to_submitted_with_warning(capsys):
    """Test that unknown statuses map to 'submitted' with a warning."""
    assert _local_status_for("weird_new_status") == "submitted"
    captured = capsys.readouterr()
    assert "unknown broker status" in captured.out
