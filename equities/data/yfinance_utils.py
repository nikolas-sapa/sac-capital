"""Helpers for calling yfinance without leaking its noisy stderr/stdout."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from typing import Callable, TypeVar


T = TypeVar("T")


def call_quietly(fn: Callable[[], T]) -> T:
    """Run *fn* while suppressing yfinance's printed warnings and errors."""
    sink = StringIO()
    with redirect_stdout(sink), redirect_stderr(sink):
        return fn()
