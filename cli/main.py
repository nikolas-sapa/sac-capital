"""`sac` — SAC Capital CLI entry point."""
from __future__ import annotations

import argparse
import os
import sys

from cli.banner import print_banner
from cli.setup import run_setup
from cli.workdir import resolve_workdir


def _run_module_main(module_main, passthrough: list[str], prog: str) -> int:
    sys.argv = [prog, *passthrough]
    module_main()
    return 0


def _research_main() -> None:
    from runner_research import main as research_main
    research_main()


def _equities_main() -> None:
    from runner_equities import main as equities_main
    equities_main()


def _doctor(passthrough: list[str]) -> int:
    from scripts.preflight import main as preflight_main
    if "--llm" in passthrough:
        from core.claude_client import ClaudeCodeClient
        print("LLM probe (one small subscription/API call)...")
        resp = ClaudeCodeClient(timeout=120).complete(
            system="Reply with exactly: OK", user="ping", model="fast")
        print(f"LLM probe response: {resp.content[:40]}")
    try:
        preflight_main()
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def _verify(passthrough: list[str]) -> int:
    from scripts.export_mantle_commitments import main as export_main
    return _run_module_main(export_main, passthrough, "export-mantle-commitments")


_COMMANDS = [
    ("setup", "interactive setup wizard"),
    ("run", "run the equities pipeline"),
    ("research", "run the research runner (flags pass through)"),
    ("doctor", "preflight checks (--llm adds a live LLM probe)"),
    ("verify", "export/verify decision commitments"),
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sac", description="SAC Capital — AI trading research agent (paper-only by default).")
    sub = parser.add_subparsers(dest="cmd")
    for name, help_text in _COMMANDS:
        sub.add_parser(name, help=help_text)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = _build_parser()

    if not argv:
        print_banner()
        parser.print_help()
        return 0

    cmd, rest = argv[0], argv[1:]
    if cmd not in dict(_COMMANDS):
        # let argparse produce the standard "invalid choice" error/usage.
        parser.parse_args(argv)
        return 2

    workdir = resolve_workdir()
    os.chdir(workdir)

    if cmd == "setup":
        return run_setup()

    # First run: no config yet → guide setup before running a command that needs it.
    if cmd in ("run", "research") and not (workdir / ".env").exists():
        print("First run — no configuration found. Launching setup.\n")
        rc = run_setup(first_run=True)
        if rc == 0:
            print(f"\nConfig saved to {workdir / '.env'}. Re-run `sac {cmd}` to continue.")
        return rc

    passthrough = [a for a in rest if a != "--"]
    if cmd == "run":
        return _run_module_main(_equities_main, passthrough, "runner-equities")
    if cmd == "research":
        return _run_module_main(_research_main, passthrough, "runner-research")
    if cmd == "doctor":
        return _doctor(passthrough)
    if cmd == "verify":
        return _verify(passthrough)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
