from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Iterable


BYTES32_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


@dataclass(frozen=True)
class CommitmentLine:
    line_number: int
    raw_line: str
    record: dict

    @property
    def decision_hash(self) -> str:
        value = self.record.get("bytes32")
        if not isinstance(value, str) or not BYTES32_RE.fullmatch(value):
            raise ValueError(f"line {self.line_number}: bytes32 must be 0x + 64 hex chars")
        return value.lower()

    @property
    def uri_fragment(self) -> str:
        return f"line-{self.line_number}"


def agent_id_to_bytes32(value: str) -> str:
    if BYTES32_RE.fullmatch(value):
        return value.lower()
    return "0x" + sha256(value.encode("utf-8")).hexdigest()


def load_commitments(path: str | Path) -> list[CommitmentLine]:
    lines: list[CommitmentLine] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
            item = CommitmentLine(line_number=line_number, raw_line=stripped, record=record)
            item.decision_hash
            lines.append(item)
    return lines


def select_commitments(items: Iterable[CommitmentLine], limit: int | None) -> list[CommitmentLine]:
    if limit is not None and limit < 1:
        raise ValueError("--limit must be greater than zero")
    selected = list(items)
    return selected if limit is None else selected[:limit]


def build_uri(uri_base: str, item: CommitmentLine) -> str:
    if not uri_base:
        return item.uri_fragment
    separator = "&" if "#" in uri_base else "#"
    return f"{uri_base}{separator}{item.uri_fragment}"


def cast_command(
    *,
    contract: str,
    agent_id: str,
    commitment: CommitmentLine,
    uri: str,
    rpc_url: str,
    private_key: str,
) -> list[str]:
    return [
        "cast",
        "send",
        contract,
        "recordDecision(bytes32,bytes32,string)",
        agent_id,
        commitment.decision_hash,
        uri,
        "--rpc-url",
        rpc_url,
        "--private-key",
        private_key,
    ]


def submit_with_cast(command: list[str]) -> str:
    if shutil.which("cast") is None:
        raise RuntimeError("cast is not installed; install Foundry or run without --send")
    try:
        result = subprocess.run(command, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"cast send failed (exit {exc.returncode}): {(exc.stderr or '').strip()}"
        ) from None
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dry-run or submit exported AI decision commitments to AgentDecisionRegistry."
    )
    parser.add_argument("--commitments", required=True, help="JSONL file from export_mantle_commitments.py")
    parser.add_argument("--contract", required=True, help="AgentDecisionRegistry address")
    parser.add_argument("--agent-id", required=True, help="bytes32 agent ID, or a name to sha256 into bytes32")
    parser.add_argument("--limit", type=int, default=1, help="number of commitments to process")
    parser.add_argument("--uri-base", default=os.getenv("PUBLIC_COMMITMENTS_URL", ""))
    parser.add_argument(
        "--network",
        choices=["sepolia", "mainnet"],
        default="sepolia",
        help="target network (default: sepolia); sets RPC URL and explorer base unless --rpc-url overrides",
    )
    parser.add_argument("--rpc-url", default="", help="override RPC URL (overrides --network default)")
    parser.add_argument("--private-key-env", default="MANTLE_PRIVATE_KEY")
    parser.add_argument("--dry-run", action="store_true", help="print planned transactions without sending")
    parser.add_argument("--send", action="store_true", help="broadcast transactions; required for on-chain writes")
    args = parser.parse_args()

    _network_defaults = {
        "sepolia": {
            "rpc_url": "https://rpc.sepolia.mantle.xyz",
            "explorer_base": "https://sepolia.mantlescan.xyz",
        },
        "mainnet": {
            "rpc_url": "https://rpc.mantle.xyz",
            "explorer_base": "https://explorer.mantle.xyz",
        },
    }
    network_cfg = _network_defaults[args.network]

    # --rpc-url flag wins; fall back to env var, then network default
    rpc_url = args.rpc_url or os.getenv("MANTLE_RPC_URL", "") or network_cfg["rpc_url"]

    if args.network == "mainnet":
        print(
            "WARNING: mainnet broadcast — double-check contract address and agent ID before confirming.",
            file=sys.stderr,
        )

    if not ADDRESS_RE.fullmatch(args.contract):
        raise SystemExit("--contract must be a 20-byte hex address")
    if args.dry_run and args.send:
        raise SystemExit("--dry-run and --send are mutually exclusive")

    commitments = select_commitments(load_commitments(args.commitments), args.limit)
    agent_id = agent_id_to_bytes32(args.agent_id)

    if args.send:
        if not rpc_url:
            raise SystemExit("MANTLE_RPC_URL or --rpc-url is required with --send")
        PRIVATE_KEY_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
        private_key = os.getenv(args.private_key_env, "")
        if not private_key:
            raise SystemExit(f"{args.private_key_env} is required with --send")
        if not PRIVATE_KEY_RE.fullmatch(private_key):
            raise SystemExit(f"--private-key-env={args.private_key_env} did not resolve to a valid 0x+64hex private key")
    else:
        private_key = ""

    for item in commitments:
        uri = build_uri(args.uri_base, item)
        print(f"line={item.line_number} commitment={item.decision_hash} uri={uri}")
        print(f"payload={item.raw_line}")
        if args.send:
            output = submit_with_cast(
                cast_command(
                    contract=args.contract,
                    agent_id=agent_id,
                    commitment=item,
                    uri=uri,
                    rpc_url=rpc_url,
                    private_key=private_key,
                )
            )
            print(output)
        else:
            print("tx=dry-run")


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
