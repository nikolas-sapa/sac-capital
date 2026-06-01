from datetime import date
from pathlib import Path

from harness.obsidian import ObsidianVault


def test_write_daily_creates_file(tmp_path):
    vault = ObsidianVault(tmp_path)
    d = date(2025, 6, 1)
    path = vault.write_daily(d, "# Test\ncontent")
    assert path.exists()
    assert path.name == "2025-06-01.md"
    assert path.read_text() == "# Test\ncontent"


def test_write_daily_is_idempotent(tmp_path):
    vault = ObsidianVault(tmp_path)
    d = date(2025, 6, 1)
    vault.write_daily(d, "first")
    vault.write_daily(d, "second")
    path = tmp_path / "daily" / "2025-06-01.md"
    assert path.read_text() == "second"


def test_append_changelog_creates_file(tmp_path):
    vault = ObsidianVault(tmp_path)
    vault.append_changelog("entry 1")
    changelog = tmp_path / "params" / "CHANGELOG.md"
    assert changelog.exists()
    assert "entry 1" in changelog.read_text()


def test_append_changelog_accumulates(tmp_path):
    vault = ObsidianVault(tmp_path)
    vault.append_changelog("a")
    vault.append_changelog("b")
    text = (tmp_path / "params" / "CHANGELOG.md").read_text()
    assert "a" in text and "b" in text


def test_write_proposal_has_approval_checkbox(tmp_path):
    vault = ObsidianVault(tmp_path)
    path = vault.write_proposal("min-edge-bump", "strategy: llm\nkey: min_edge\nvalue: 0.10")
    content = path.read_text()
    assert "- [ ] Approved" in content
    assert "min_edge" in content


def test_update_index_rewrites_file(tmp_path):
    vault = ObsidianVault(tmp_path)
    vault.update_index({"bankroll": "1000.00", "open": 3})
    vault.update_index({"bankroll": "1050.00", "open": 2})
    index = (tmp_path / "index.md").read_text()
    assert "1050.00" in index
    assert "1000.00" not in index
