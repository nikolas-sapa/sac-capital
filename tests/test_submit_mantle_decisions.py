from __future__ import annotations

import json

import pytest

from scripts.submit_mantle_decisions import (
    agent_id_to_bytes32,
    build_uri,
    cast_command,
    load_commitments,
    select_commitments,
)


def _record(hash_value: str = "0x" + "a" * 64) -> str:
    return json.dumps({"bytes32": hash_value, "payload": {"question": "Will Mantle verify AI?"}})


def test_load_commitments_validates_bytes32(tmp_path) -> None:
    path = tmp_path / "commitments.jsonl"
    path.write_text(_record() + "\n", encoding="utf-8")

    items = load_commitments(path)

    assert len(items) == 1
    assert items[0].line_number == 1
    assert items[0].decision_hash == "0x" + "a" * 64


def test_load_commitments_rejects_bad_hash(tmp_path) -> None:
    path = tmp_path / "commitments.jsonl"
    path.write_text(_record("bad") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="bytes32"):
        load_commitments(path)


def test_select_commitments_honors_limit(tmp_path) -> None:
    path = tmp_path / "commitments.jsonl"
    path.write_text(_record("0x" + "a" * 64) + "\n" + _record("0x" + "b" * 64) + "\n", encoding="utf-8")

    selected = select_commitments(load_commitments(path), 1)

    assert len(selected) == 1
    assert selected[0].decision_hash == "0x" + "a" * 64


def test_select_commitments_rejects_non_positive_limit(tmp_path) -> None:
    path = tmp_path / "commitments.jsonl"
    path.write_text(_record() + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="greater than zero"):
        select_commitments(load_commitments(path), 0)


def test_agent_id_accepts_bytes32_or_hashes_name() -> None:
    explicit = "0x" + "c" * 64

    assert agent_id_to_bytes32(explicit.upper().replace("X", "x")) == explicit
    assert agent_id_to_bytes32("mantle-agent").startswith("0x")
    assert len(agent_id_to_bytes32("mantle-agent")) == 66


def test_build_uri_uses_line_fragment(tmp_path) -> None:
    path = tmp_path / "commitments.jsonl"
    path.write_text(_record() + "\n", encoding="utf-8")
    item = load_commitments(path)[0]

    assert build_uri("", item) == "line-1"
    assert build_uri("https://example.com/commitments.jsonl", item).endswith("#line-1")


def test_cast_command_targets_record_decision(tmp_path) -> None:
    path = tmp_path / "commitments.jsonl"
    path.write_text(_record() + "\n", encoding="utf-8")
    item = load_commitments(path)[0]

    command = cast_command(
        contract="0x" + "1" * 40,
        agent_id="0x" + "2" * 64,
        commitment=item,
        uri="https://example.com/commitments.jsonl#line-1",
        rpc_url="https://rpc.test",
        private_key="0xsecret",
    )

    assert command[:4] == [
        "cast",
        "send",
        "0x" + "1" * 40,
        "recordDecision(bytes32,bytes32,string)",
    ]
    assert item.decision_hash in command
