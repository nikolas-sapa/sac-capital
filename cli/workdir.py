"""Resolve the directory sac runs from.

All existing code reads `.env` and `data/...` relative to CWD. Instead of
refactoring those paths, the CLI chdirs to a stable home directory unless
it is launched inside a checkout (marked by a `.env` in CWD).
"""
from __future__ import annotations

import os
from pathlib import Path


def resolve_workdir(cwd: Path | None = None) -> Path:
    cwd = cwd or Path.cwd()
    if (cwd / ".env").exists():
        return cwd
    home = Path(os.environ.get("SAC_HOME", str(Path.home() / ".sac-capital")))
    (home / "data").mkdir(parents=True, exist_ok=True)
    return home
