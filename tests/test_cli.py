"""Tests for the sac CLI (banner, workdir, wizard, dispatch)."""
from __future__ import annotations


class TestBanner:
    def test_banner_contains_wordmark(self):
        from cli.banner import BANNER
        assert "SAC" in BANNER

    def test_print_banner_includes_disclaimer(self, capsys):
        from cli.banner import print_banner
        print_banner()
        out = capsys.readouterr().out
        assert "paper-only" in out.lower()


class TestWorkdir:
    def test_repo_mode_when_env_in_cwd(self, tmp_path):
        from cli.workdir import resolve_workdir
        (tmp_path / ".env").write_text("X=1\n")
        assert resolve_workdir(cwd=tmp_path) == tmp_path

    def test_home_mode_creates_dirs(self, tmp_path, monkeypatch):
        from cli.workdir import resolve_workdir
        home = tmp_path / "sachome"
        monkeypatch.setenv("SAC_HOME", str(home))
        result = resolve_workdir(cwd=tmp_path)  # no .env in cwd
        assert result == home
        assert (home / "data").is_dir()

    def test_default_home_under_user_home(self, tmp_path, monkeypatch):
        from cli.workdir import resolve_workdir
        monkeypatch.delenv("SAC_HOME", raising=False)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        result = resolve_workdir(cwd=tmp_path / "elsewhere")
        assert result == tmp_path / ".sac-capital"


def make_answers(answers):
    it = iter(answers)
    return lambda prompt="": next(it, "")


class TestWizard:
    def test_subscription_default_when_claude_on_path(self):
        from cli.setup import run_wizard
        # accept every default: press enter through all prompts
        env = run_wizard(input_fn=make_answers([""] * 20),
                         which=lambda cmd: "/usr/local/bin/claude")
        assert env["LLM_PROVIDER"] == "claude_cli"
        assert "LIVE_TRADING_ENABLED" not in env
        assert env["BANKROLL_USD"] == "1000"

    def test_api_key_fallback_when_no_claude(self):
        from cli.setup import run_wizard
        # provider menu: 1=anthropic key, then the key, then defaults
        env = run_wizard(input_fn=make_answers(["1", "sk-ant-xyz"] + [""] * 20),
                         which=lambda cmd: None)
        assert env["LLM_PROVIDER"] == "anthropic"
        assert env["ANTHROPIC_API_KEY"] == "sk-ant-xyz"

    def test_alpaca_skip_uses_internal_paper(self):
        from cli.setup import run_wizard
        env = run_wizard(input_fn=make_answers([""] * 20),
                         which=lambda cmd: "/bin/claude")
        assert env["EXECUTION_PROVIDER"] == "internal_paper"
        assert "ALPACA_API_KEY_ID" not in env

    def test_write_env_refuses_overwrite(self, tmp_path):
        from cli.setup import write_env
        target = tmp_path / ".env"
        target.write_text("OLD=1\n")
        ok = write_env({"A": "1"}, target, input_fn=make_answers(["n"]))
        assert ok is False
        assert target.read_text() == "OLD=1\n"

    def test_write_env_writes_pairs(self, tmp_path):
        from cli.setup import write_env
        target = tmp_path / ".env"
        ok = write_env({"A": "1", "B": "two"}, target)
        assert ok is True
        assert target.read_text() == "A=1\nB=two\n"

    def test_write_env_rejects_newline_injection(self, tmp_path):
        import pytest
        from cli.setup import write_env
        target = tmp_path / ".env"
        with pytest.raises(ValueError):
            write_env({"A": "sk-ant-x\nLIVE_TRADING_ENABLED=true"}, target)
        assert not target.exists()

    def test_write_env_sets_permissions_0600(self, tmp_path):
        from cli.setup import write_env
        target = tmp_path / ".env"
        write_env({"A": "1"}, target)
        assert (target.stat().st_mode & 0o777) == 0o600

    def test_write_env_tightens_perms_on_preexisting_0644_file(self, tmp_path):
        import os
        from cli.setup import write_env
        target = tmp_path / ".env"
        target.write_text("OLD=1\n")
        os.chmod(target, 0o644)
        ok = write_env({"A": "1"}, target, input_fn=make_answers(["y"]))
        assert ok is True
        assert (target.stat().st_mode & 0o777) == 0o600
