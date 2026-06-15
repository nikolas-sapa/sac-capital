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
    # Real equity decision reasoning (approved + rejected) is the canonical
    # source anchored on-chain. The Polymarket ledger is opt-in (legacy/dummy
    # signals) — pass --ledger explicitly to include it.
    parser.add_argument("--ledger", default="")
    parser.add_argument("--research-artifacts", default="data/research_artifacts.jsonl")
    parser.add_argument("--open-only", action="store_true")
    parser.add_argument(
        "--exclude-infra",
        action="store_true",
        help="Drop data-infra non-decisions (decision=error, rejection_reason=invalid_or_stale_price) "
             "so only substantive AI decisions are anchored.",
    )
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    commitments = list(research_artifact_commitments(args.research_artifacts))
    if args.ledger:
        commitments.extend(
            export_ledger_commitments(args.ledger, include_resolved=not args.open_only)
        )

    if args.exclude_infra:
        _INFRA_REASONS = {"invalid_or_stale_price"}
        commitments = [
            c for c in commitments
            if c.payload.get("decision") != "error"
            and c.payload.get("rejection_reason") not in _INFRA_REASONS
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
