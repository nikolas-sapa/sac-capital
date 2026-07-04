# cli/setup.py
"""Interactive `sac setup` wizard. Stdlib only; every step skippable."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from cli.banner import print_banner
from cli.workdir import resolve_workdir

RISK_DEFAULTS = {
    "BANKROLL_USD": "1000",
    "KELLY_FRACTION": "0.5",
    "MAX_POSITION_PCT": "0.02",
    "MAX_ORDER_USD": "25",
    "MAX_DAILY_ORDER_COUNT": "10",
}


def _ask(input_fn, label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input_fn(f"{label}{suffix}: ").strip()
    return answer or default


def run_wizard(input_fn=input, which=shutil.which) -> dict[str, str]:
    env: dict[str, str] = {}

    # 1. LLM auth — subscription first
    if which("claude"):
        print("Found `claude` CLI — using your Claude subscription (no API key).")
        choice = _ask(input_fn, "LLM provider — Enter=subscription, 1=Anthropic API key, 2=OpenAI key, 3=Codex CLI", "")
    else:
        print("`claude` CLI not found — install it for subscription mode (npm i -g @anthropic-ai/claude-code).")
        choice = _ask(input_fn, "LLM provider — 1=Anthropic API key, 2=OpenAI key, 3=Codex CLI", "1")
    if choice == "1":
        env["LLM_PROVIDER"] = "anthropic"
        env["ANTHROPIC_API_KEY"] = _ask(input_fn, "ANTHROPIC_API_KEY")
    elif choice == "2":
        env["LLM_PROVIDER"] = "openai"
        env["OPENAI_API_KEY"] = _ask(input_fn, "OPENAI_API_KEY")
    elif choice == "3":
        env["LLM_PROVIDER"] = "codex"
    else:
        env["LLM_PROVIDER"] = "claude_cli"

    # 2. Alpaca paper keys (optional)
    key_id = _ask(input_fn, "Alpaca paper API key id (Enter to skip — internal paper ledger)")
    if key_id:
        env["ALPACA_API_KEY_ID"] = key_id
        env["ALPACA_SECRET_KEY"] = _ask(input_fn, "Alpaca secret key")
        env["ALPACA_PAPER"] = "true"
        env["EXECUTION_PROVIDER"] = "alpaca_paper"
    else:
        env["EXECUTION_PROVIDER"] = "internal_paper"

    # 3. Tiingo (optional)
    tiingo = _ask(input_fn, "Tiingo API key (Enter to skip — yfinance only)")
    if tiingo:
        env["TIINGO_API_KEY"] = tiingo

    # 4. Telegram (optional)
    tg = _ask(input_fn, "Telegram bot token (Enter to skip)")
    if tg:
        env["TELEGRAM_BOT_TOKEN"] = tg
        env["TELEGRAM_CHAT_ID"] = _ask(input_fn, "Telegram chat id")

    # 5. Mantle anchoring (optional, off by default)
    if _ask(input_fn, "Enable Mantle on-chain anchoring? [y/N]", "n").lower() == "y":
        env["MANTLE_RPC_URL"] = _ask(input_fn, "Mantle RPC URL", "https://rpc.sepolia.mantle.xyz")
        env["MANTLE_PRIVATE_KEY"] = _ask(input_fn, "Deployer private key (testnet-only wallet!)")
        env["AGENT_REGISTRY_ADDRESS"] = _ask(input_fn, "AgentDecisionRegistry address")

    # 6. Risk params — accept defaults or edit
    for key, default in RISK_DEFAULTS.items():
        env[key] = _ask(input_fn, key, default)

    # ponytail: wizard never writes LIVE_TRADING_ENABLED — paper-only stays the hard default
    return env


def write_env(env: dict[str, str], path: Path, input_fn=input) -> bool:
    for k, v in env.items():
        if "\n" in k or "\r" in k or "=" in k:
            raise ValueError(f"invalid env key: {k!r}")
        if "\n" in v or "\r" in v:
            raise ValueError(f"invalid env value for {k!r}: contains newline")
    if path.exists():
        if _ask(input_fn, f"{path} exists — overwrite? [y/N]", "n").lower() != "y":
            print("Keeping existing .env.")
            return False
    path.write_text("".join(f"{k}={v}\n" for k, v in env.items()))
    os.chmod(path, 0o600)
    print(f"Wrote {path}")
    return True


def run_setup(input_fn=input) -> int:
    print_banner()
    workdir = resolve_workdir()
    print(f"Working directory: {workdir}")
    env = run_wizard(input_fn=input_fn)
    if not write_env(env, workdir / ".env", input_fn=input_fn):
        return 1
    print("Setup complete. Next: `sac doctor` to verify, then `sac run`.")
    return 0
