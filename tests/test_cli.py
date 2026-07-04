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
