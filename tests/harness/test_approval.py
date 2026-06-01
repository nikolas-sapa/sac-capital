import pytest
from harness.approval import classify_change, apply_approved
from harness.obsidian import ObsidianVault
from harness.params import ParamStore


def test_auto_within_cap():
    assert classify_change("min_edge", 0.08, 0.10, {"min_edge": 0.05}) == "auto"


def test_approval_beyond_cap():
    assert classify_change("min_edge", 0.08, 0.20, {"min_edge": 0.05}) == "approval"


def test_approval_for_unknown_key():
    assert classify_change("enable_strategy", True, False, {}) == "approval"


def test_auto_at_exact_cap():
    assert classify_change("x", 0.0, 0.05, {"x": 0.05}) == "auto"


def test_apply_approved_picks_up_checked_proposals(tmp_path):
    vault = ObsidianVault(tmp_path)
    store = ParamStore(tmp_path / "p.db")

    # Write a proposal manually with the checkbox checked
    path = vault._root / "proposals" / "2025-06-01-llm-min_edge.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "strategy: llm\nkey: min_edge\nvalue: 0.10\nreason: manual test\n\n- [x] Approved\n"
    )

    applied = apply_approved(vault, store)
    assert len(applied) == 1
    assert store.get("llm", "min_edge") == pytest.approx(0.10)


def test_apply_approved_ignores_unchecked(tmp_path):
    vault = ObsidianVault(tmp_path)
    store = ParamStore(tmp_path / "p.db")

    path = vault._root / "proposals" / "2025-06-01-llm-min_conf.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "strategy: llm\nkey: min_conf\nvalue: 0.60\n\n- [ ] Approved\n"
    )

    applied = apply_approved(vault, store)
    assert applied == []
    assert store.get("llm", "min_conf") is None


def test_apply_approved_empty_dir(tmp_path):
    vault = ObsidianVault(tmp_path)
    store = ParamStore(tmp_path / "p.db")
    assert apply_approved(vault, store) == []
