"""Detached equities service runner for environments where launchd bootstrap is blocked.

The service performs an immediate full scan on startup, then continues with:
- hourly mark-to-market / exit checks
- one full equities scan every 24 hours

It is intentionally simple and process-based so it can be started with `nohup`
or any other supervisor when launchd is unavailable from the current session.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
MARK_INTERVAL_SECONDS = 3600
SCAN_INTERVAL_SECONDS = 24 * 3600


def _run_runner(args: list[str]) -> int:
    env = os.environ.copy()
    local_bin = str(Path.home() / ".local/bin")
    path = env.get("PATH", "")
    env["PATH"] = f"{local_bin}:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:{path}"
    cmd = [str(PYTHON), str(ROOT / "runner_equities.py"), *args]
    print(f"[SERVICE] running: {' '.join(cmd)}", flush=True)
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        check=False,
    )
    elapsed = time.time() - started
    print(f"[SERVICE] exit={proc.returncode} elapsed_s={elapsed:.1f}", flush=True)
    return proc.returncode


def _sleep_until(deadline: float) -> None:
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 60.0))


def main() -> None:
    print("[SERVICE] equities service starting", flush=True)
    next_mark = time.time()
    next_scan = time.time()
    while True:
        now = time.time()
        if now >= next_mark:
            _run_runner(["--mark-only"])
            next_mark = time.time() + MARK_INTERVAL_SECONDS

        now = time.time()
        if now >= next_scan:
            _run_runner([])
            next_scan = time.time() + SCAN_INTERVAL_SECONDS

        _sleep_until(min(next_mark, next_scan))


if __name__ == "__main__":
    main()
