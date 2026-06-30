"""Helpers for calling yfinance without leaking its noisy stderr/stdout."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import multiprocessing as mp
from typing import Any, Callable, TypeVar


T = TypeVar("T")


def call_quietly(fn: Callable[[], T]) -> T:
    """Run *fn* while suppressing yfinance's printed warnings and errors."""
    sink = StringIO()
    with redirect_stdout(sink), redirect_stderr(sink):
        return fn()


def _call_worker(conn, fn: Callable[..., Any]) -> None:
    while True:
        try:
            args = conn.recv()
        except EOFError:
            return
        try:
            conn.send(("ok", fn(*args)))
        except BaseException as exc:
            conn.send(("error", f"{type(exc).__name__}: {exc}"))


class IsolatedCall:
    """Persistent provider worker that can be killed and restarted after a timeout."""

    def __init__(self, fn: Callable[..., T], timeout: float) -> None:
        self._fn = fn
        self._timeout = timeout
        self._process = None
        self._parent = None

    def __call__(self, *args: Any) -> T:
        self._start()
        self._parent.send(args)
        if not self._parent.poll(self._timeout):
            self._stop()
            raise TimeoutError(f"timeout after {self._timeout:g}s")
        status, payload = self._parent.recv()
        if status == "error":
            raise RuntimeError(payload)
        return payload

    def _start(self) -> None:
        if self._process is not None and self._process.is_alive():
            return
        context = mp.get_context("spawn")
        self._parent, child = context.Pipe()
        self._process = context.Process(
            target=_call_worker,
            args=(child, self._fn),
            daemon=True,
        )
        self._process.start()
        child.close()

    def _stop(self) -> None:
        if self._parent is not None:
            self._parent.close()
            self._parent = None
        if self._process is not None:
            self._process.terminate()
            self._process.join(1)
            if self._process.is_alive():
                self._process.kill()
                self._process.join()
            self._process = None

    def __del__(self) -> None:
        self._stop()
