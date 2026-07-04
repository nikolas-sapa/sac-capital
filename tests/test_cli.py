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
