from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hackathon.verifiability import (
    export_ledger_commitments,
    records_to_jsonl,
    research_artifact_commitments,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export deterministic decision hashes for Mantle anchoring."
    )
    parser.add_argument("--ledger", default="data/ledger.db")
    parser.add_argument("--research-artifacts", default="data/research_artifacts.jsonl")
    parser.add_argument("--open-only", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    commitments = [
        *export_ledger_commitments(args.ledger, include_resolved=not args.open_only),
        *research_artifact_commitments(args.research_artifacts),
    ]
    text = records_to_jsonl(commitment.as_record() for commitment in commitments)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + ("\n" if text else ""), encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
