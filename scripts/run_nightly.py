"""Launchd entrypoint for nightly self-improvement consolidation."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.ledger import Ledger
from harness.nightly import run_nightly
from harness.obsidian import ObsidianVault
from harness.params import ParamStore


def main() -> None:
    ledger = Ledger("data/ledger.db")
    store = ParamStore("data/params.db")
    vault = ObsidianVault("data/obsidian")
    try:
        result = run_nightly(
            ledger=ledger,
            store=store,
            vault=vault,
            learners=[],
        )
        print(
            "nightly complete: "
            f"auto={len(result['auto_applied'])} "
            f"queued={len(result['approval_queued'])} "
            f"approved={len(result['approved_applied'])}"
        )
    finally:
        ledger.close()
        store.close()


if __name__ == "__main__":
    main()
