"""ASCII wordmark for the SAC Capital CLI."""
from __future__ import annotations

BANNER = r"""
  ███████╗ █████╗  ██████╗     ██████╗ █████╗ ██████╗ ██╗████████╗ █████╗ ██╗
  ██╔════╝██╔══██╗██╔════╝    ██╔════╝██╔══██╗██╔══██╗██║╚══██╔══╝██╔══██╗██║
  ███████╗███████║██║         ██║     ███████║██████╔╝██║   ██║   ███████║██║
  ╚════██║██╔══██║██║         ██║     ██╔══██║██╔═══╝ ██║   ██║   ██╔══██║██║
  ███████║██║  ██║╚██████╗    ╚██████╗██║  ██║██║     ██║   ██║   ██║  ██║███████╗
  ╚══════╝╚═╝  ╚═╝ ╚═════╝     ╚═════╝╚═╝  ╚═╝╚═╝     ╚═╝   ╚═╝   ╚═╝  ╚═╝╚══════╝

  SAC CAPITAL
"""

DISCLAIMER = "AI trading research agent — paper-only by default. Not financial advice."


def print_banner() -> None:
    print(BANNER)
    print(f"  {DISCLAIMER}\n")
