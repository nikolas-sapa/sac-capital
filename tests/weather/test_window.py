from datetime import datetime, timezone, timedelta
from strategies.weather.window import in_window


def _end(hours: float) -> datetime:
    return datetime.now(tz=timezone.utc) + timedelta(hours=hours)


def test_19h_is_in_window():
    assert in_window(_end(19)) is True


def test_18h_is_in_window():
    assert in_window(_end(18.1)) is True  # tiny buffer for test clock drift


def test_30h_is_in_window():
    assert in_window(_end(30)) is True


def test_17h_is_outside_window():
    assert in_window(_end(17)) is False


def test_31h_is_outside_window():
    assert in_window(_end(31)) is False


def test_5h_is_outside_window():
    assert in_window(_end(5)) is False
