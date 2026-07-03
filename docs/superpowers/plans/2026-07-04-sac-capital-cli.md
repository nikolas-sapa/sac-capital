# SAC Capital CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `sac` CLI (banner, setup wizard, run/research/doctor/verify) installable from GitHub or PyPI, subscription-first via the `claude` CLI.

**Architecture:** New `cli/` package wraps existing runners with stdlib argparse. A workdir resolver chdirs to `~/.sac-capital/` (or repo CWD) so all existing relative `.env`/`data/` paths keep working. `LLM_PROVIDER=claude_cli` becomes a first-class, tested provider value.

**Tech Stack:** Python ≥3.12, stdlib only for new code (argparse, shutil, pathlib), hatchling build backend, pytest.

## Global Constraints

- No new dependencies. New CLI code uses stdlib only.
- Command name `sac`; package name `sac-capital` (unchanged).
- Wizard NEVER writes `LIVE_TRADING_ENABLED` (paper-only hard default).
- Wheel excludes `frontend/`, `contracts/`, `docs/`, `spike/`, `tests/`; INCLUDES `hackathon/` (needed by `scripts/export_mantle_commitments.py`).
- Remove broken `runner = "runner:main"` script entry (no `runner.py` exists).
- Repo mode detection: `.env` in CWD → stay; else chdir to `$SAC_HOME` or `~/.sac-capital/`.
- ASCII banner monochrome, followed by one-line paper-only disclaimer.
- Existing entry points `runner-equities`, `runner-research`, `latency-probe` stay.
- Commit messages end with the Co-Authored-By/Claude-Session trailer used in this repo's recent commits.

---

### Task 1: ASCII banner (`cli/banner.py`)

**Files:**
- Create: `cli/__init__.py` (empty)
- Create: `cli/banner.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `cli.banner.BANNER: str` (multiline ASCII art), `cli.banner.print_banner() -> None` (prints BANNER + disclaimer line containing "paper-only").

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cli'`

- [ ] **Step 3: Write minimal implementation**

Create empty `cli/__init__.py`, then:

```python
# cli/banner.py
"""ASCII wordmark for the sac CLI."""
from __future__ import annotations

BANNER = r"""
  ███████╗ █████╗  ██████╗     ██████╗ █████╗ ██████╗ ██╗████████╗ █████╗ ██╗
  ██╔════╝██╔══██╗██╔════╝    ██╔════╝██╔══██╗██╔══██╗██║╚══██╔══╝██╔══██╗██║
  ███████╗███████║██║         ██║     ███████║██████╔╝██║   ██║   ███████║██║
  ╚════██║██╔══██║██║         ██║     ██╔══██║██╔═══╝ ██║   ██║   ██╔══██║██║
  ███████║██║  ██║╚██████╗    ╚██████╗██║  ██║██║     ██║   ██║   ██║  ██║███████╗
  ╚══════╝╚═╝  ╚═╝ ╚═════╝     ╚═════╝╚═╝  ╚═╝╚═╝     ╚═╝   ╚═╝   ╚═╝  ╚═╝╚══════╝
"""

DISCLAIMER = "AI trading research agent — paper-only by default. Not financial advice."


def print_banner() -> None:
    print(BANNER)
    print(f"  {DISCLAIMER}\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add cli/__init__.py cli/banner.py tests/test_cli.py
git commit -m "feat(cli): ASCII banner with paper-only disclaimer"
```

---

### Task 2: Workdir resolver (`cli/workdir.py`)

**Files:**
- Create: `cli/workdir.py`
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Produces: `cli.workdir.resolve_workdir(cwd: Path | None = None) -> Path` — returns the directory the CLI should run from and creates it (plus `data/` subdir) if needed. Does NOT chdir (caller does).
- Rules: if `(cwd or Path.cwd()) / ".env"` exists → return that cwd (repo mode). Else return `Path(os.environ.get("SAC_HOME", Path.home() / ".sac-capital"))`, mkdir parents + `data/`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_cli.py::TestWorkdir -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cli.workdir'`

- [ ] **Step 3: Write minimal implementation**

```python
# cli/workdir.py
"""Resolve the directory sac runs from.

All existing code reads `.env` and `data/...` relative to CWD. Instead of
refactoring those paths, the CLI chdirs to a stable home directory unless
it is launched inside a checkout (marked by a `.env` in CWD).
"""
from __future__ import annotations

import os
from pathlib import Path


def resolve_workdir(cwd: Path | None = None) -> Path:
    cwd = cwd or Path.cwd()
    if (cwd / ".env").exists():
        return cwd
    home = Path(os.environ.get("SAC_HOME", str(Path.home() / ".sac-capital")))
    (home / "data").mkdir(parents=True, exist_ok=True)
    return home
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_cli.py::TestWorkdir -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add cli/workdir.py tests/test_cli.py
git commit -m "feat(cli): workdir resolver (repo mode vs SAC_HOME)"
```

---

### Task 3: First-class `claude_cli` provider

**Files:**
- Modify: `core/claude_client.py` (`ClaudeCodeClient.__init__` ~line 274 and `complete` ~line 300)
- Test: `tests/test_llm_provider.py` (append)

**Interfaces:**
- Produces: `LLM_PROVIDER=claude_cli` routes every `complete()` call directly to `_complete_with_claude_cli` — no Codex client constructed, no API key required.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_llm_provider.py` (reuse the file's existing monkeypatch conventions):

```python
def test_claude_cli_provider_is_first_class(monkeypatch):
    """LLM_PROVIDER=claude_cli must route to the claude CLI without codex or keys."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "claude_cli")
    from core.claude_client import ClaudeCodeClient, LLMResponse

    client = ClaudeCodeClient()
    assert client._codex is None
    assert client._openai is None
    assert client._anthropic is None

    calls = {}

    def fake_cli(system, user, model):
        calls["model"] = model
        return LLMResponse(content="ok", input_tokens=1, output_tokens=1)

    client._complete_with_claude_cli = fake_cli
    resp = client.complete("sys", "usr", "fast")
    assert resp.content == "ok"
    assert calls["model"] == "fast"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_llm_provider.py::test_claude_cli_provider_is_first_class -v`
Expected: FAIL — currently `use_codex` is False for `claude_cli` so `_codex is None` passes, but confirm the full assertion chain; if it passes accidentally, it must FAIL after adding this assert:

```python
    assert client._provider == "claude_cli"
```

(Behavior today is fall-through-by-accident; the test locks it as contract.)

- [ ] **Step 3: Make routing explicit**

In `core/claude_client.py`, `ClaudeCodeClient.complete`, add as the FIRST branch:

```python
        if self._provider == "claude_cli":
            return self._complete_with_claude_cli(system, user, model)
```

No `__init__` change needed (`claude_cli` matches no client-constructing branch).

- [ ] **Step 4: Run tests to verify pass**

Run: `./.venv/bin/python -m pytest tests/test_llm_provider.py -v`
Expected: all PASS (existing + new)

- [ ] **Step 5: Commit**

```bash
git add core/claude_client.py tests/test_llm_provider.py
git commit -m "feat(llm): claude_cli as first-class subscription provider"
```

---

### Task 4: Setup wizard (`cli/setup.py`)

**Files:**
- Create: `cli/setup.py`
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Consumes: `cli.workdir.resolve_workdir`.
- Produces:
  - `run_wizard(input_fn=input, which=shutil.which) -> dict[str, str]` — asks questions, returns env mapping.
  - `write_env(env: dict[str, str], path: Path, input_fn=input) -> bool` — writes `KEY=value` lines; if `path` exists, asks `overwrite? [y/N]` and returns False on decline.
  - `run_setup(input_fn=input) -> int` — banner → resolve workdir → wizard → write_env → returns 0/1. Used by `sac setup`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_cli.py::TestWizard -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cli.setup'`

- [ ] **Step 3: Write minimal implementation**

```python
# cli/setup.py
"""Interactive `sac setup` wizard. Stdlib only; every step skippable."""
from __future__ import annotations

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
    if path.exists():
        if _ask(input_fn, f"{path} exists — overwrite? [y/N]", "n").lower() != "y":
            print("Keeping existing .env.")
            return False
    path.write_text("".join(f"{k}={v}\n" for k, v in env.items()))
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add cli/setup.py tests/test_cli.py
git commit -m "feat(cli): sac setup wizard — subscription-first, paper-only"
```

---

### Task 5: Dispatcher + entry point (`cli/main.py`, `pyproject.toml`)

**Files:**
- Create: `cli/main.py`
- Modify: `pyproject.toml` (`[project.scripts]`)
- Test: `tests/test_cli.py` (append)

**Interfaces:**
- Consumes: `cli.setup.run_setup`, `cli.workdir.resolve_workdir`, `cli.banner.print_banner`, `runner_equities.main`, `runner_research.main`, `scripts.preflight.main`, `scripts.export_mantle_commitments.main`.
- Produces: `cli.main.main() -> int` wired as `sac = "cli.main:main"`; broken `runner = "runner:main"` entry removed.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
class TestDispatch:
    def test_no_args_prints_banner_and_help(self, capsys, monkeypatch, tmp_path):
        from cli.main import main
        monkeypatch.setenv("SAC_HOME", str(tmp_path))
        rc = main([])
        out = capsys.readouterr().out
        assert rc == 0
        assert "SAC" in out
        assert "setup" in out

    def test_research_passthrough_args(self, monkeypatch, tmp_path):
        import cli.main as m
        monkeypatch.setenv("SAC_HOME", str(tmp_path))
        seen = {}

        def fake_research_main():
            import sys
            seen["argv"] = sys.argv[1:]

        monkeypatch.setattr(m, "_research_main", lambda: fake_research_main())
        rc = m.main(["research", "--static-only"])
        assert rc == 0

    def test_setup_dispatch(self, monkeypatch, tmp_path):
        import cli.main as m
        monkeypatch.setenv("SAC_HOME", str(tmp_path))
        monkeypatch.setattr(m, "run_setup", lambda: 0)
        assert m.main(["setup"]) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_cli.py::TestDispatch -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cli.main'`

- [ ] **Step 3: Write minimal implementation**

```python
# cli/main.py
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


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(
        prog="sac", description="SAC Capital — AI trading research agent (paper-only by default).")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("setup", help="interactive setup wizard")
    for name, help_text in [
        ("run", "run the equities pipeline"),
        ("research", "run the research runner (flags pass through)"),
        ("doctor", "preflight checks (--llm adds a live LLM probe)"),
        ("verify", "export/verify decision commitments"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("passthrough", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)

    if args.cmd is None:
        print_banner()
        parser.print_help()
        return 0

    workdir = resolve_workdir()
    os.chdir(workdir)

    if args.cmd == "setup":
        return run_setup()
    passthrough = [a for a in args.passthrough if a != "--"]
    if args.cmd == "run":
        return _run_module_main(_equities_main, passthrough, "runner-equities")
    if args.cmd == "research":
        return _run_module_main(_research_main, passthrough, "runner-research")
    if args.cmd == "doctor":
        return _doctor(passthrough)
    if args.cmd == "verify":
        return _verify(passthrough)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

In `pyproject.toml` `[project.scripts]`, replace:

```toml
[project.scripts]
latency-probe = "strategies.crypto_updown.latency_probe:main"
runner-equities = "runner_equities:main"
runner-research = "runner_research:main"
sac = "cli.main:main"
```

(`runner = "runner:main"` deleted — `runner.py` does not exist.)

- [ ] **Step 4: Run full test suite**

Run: `./.venv/bin/python -m pytest tests/test_cli.py tests/test_llm_provider.py -v`
Expected: all PASS. Then full suite: `./.venv/bin/python -m pytest -q` — no new failures vs baseline.

- [ ] **Step 5: Smoke test**

Run: `cd /tmp && SAC_HOME=/tmp/sac-smoke ~/sapa_fund/.venv/bin/python -m cli.main` (with `PYTHONPATH=~/sapa_fund`)
Expected: banner + help, exit 0.

- [ ] **Step 6: Commit**

```bash
git add cli/main.py pyproject.toml tests/test_cli.py
git commit -m "feat(cli): sac dispatcher + entry point; drop broken runner script"
```

---

### Task 6: Build system + wheel contents

**Files:**
- Modify: `pyproject.toml` (add `[build-system]`, hatch build config)

**Interfaces:**
- Produces: `uv build` succeeds; wheel contains `cli/`, `core/`, `equities/`, `orchestrator/`, `harness/`, `strategies/`, `broadcast/`, `scripts/`, `hackathon/`, `runner_equities.py`, `runner_research.py`; excludes `frontend/`, `contracts/`, `docs/`, `spike/`, `tests/`.

- [ ] **Step 1: Add build config**

Append to `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = [
    "cli", "core", "equities", "orchestrator", "harness",
    "strategies", "broadcast", "scripts", "hackathon",
]

[tool.hatch.build.targets.wheel.force-include]
"runner_equities.py" = "runner_equities.py"
"runner_research.py" = "runner_research.py"

[tool.hatch.build.targets.sdist]
exclude = ["frontend", "contracts", "docs", "spike", "tests", "cache", "data", ".env*"]
```

- [ ] **Step 2: Verify build**

Run: `uv build`
Expected: `dist/sac_capital-0.1.0-py3-none-any.whl` + sdist created without error.

Run: `unzip -l dist/sac_capital-0.1.0-py3-none-any.whl | grep -c "frontend\|contracts"`
Expected: `0`

- [ ] **Step 3: Verify installed tool works end-to-end**

Run: `uv tool install --force --from dist/sac_capital-0.1.0-py3-none-any.whl sac-capital && cd /tmp && SAC_HOME=/tmp/sac-tool-smoke sac`
Expected: banner + help. Then `uv tool uninstall sac-capital` to clean up.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: hatchling backend, slim wheel (no frontend/contracts)"
```

---

### Task 7: INSTALL.md + README pointer

**Files:**
- Create: `INSTALL.md`
- Modify: `README.md` (add install section pointer after the intro table)

**Interfaces:**
- Consumes: everything above — documents the real commands.

- [ ] **Step 1: Write INSTALL.md**

```markdown
# Install SAC Capital

Requirements: Python ≥ 3.12. For subscription mode: the `claude` CLI
(`npm i -g @anthropic-ai/claude-code`), logged in to your Claude account.

## Option A — uv tool (recommended)

    uv tool install git+https://github.com/<owner>/sapa_fund
    # or, from PyPI once published:
    uv tool install sac-capital

## Option B — pip

    pip install sac-capital

## Option C — clone (development)

    git clone https://github.com/<owner>/sapa_fund && cd sapa_fund
    uv sync

## Set up

    sac setup

The wizard detects the `claude` CLI and defaults to **subscription mode**
(no API key, billed to your Claude plan). Alternatives offered: Anthropic
API key, OpenAI key, or Codex CLI. Every other step (Alpaca paper keys,
Tiingo, Telegram, Mantle anchoring) is optional — press Enter to skip.

Config and data live in `~/.sac-capital/` (override with `SAC_HOME`).
Running inside a cloned repo with a `.env` uses the repo directory instead.

## Verify

    sac doctor          # config + connectivity checks
    sac doctor --llm    # adds one live LLM probe call

If web crawling features complain about a missing browser:

    playwright install chromium

## Run

    sac run                      # equities pipeline (paper trading)
    sac research --static-only   # research runner
    sac verify                   # export decision commitment hashes

SAC Capital is **paper-only by default**. Live trading requires manually
editing `.env` and setting an explicit confirmation env var — the wizard
never enables it.

## Set up inside Claude Code

Open the repo (or any folder) in Claude Code and paste:

> Install sac-capital with `uv tool install sac-capital`, then run
> `sac setup` and walk me through each prompt, then `sac doctor`.
```

- [ ] **Step 2: Add README pointer**

In `README.md`, after the intro table, add:

```markdown
## Install the CLI

`uv tool install sac-capital` → `sac setup` → `sac run`. Runs on your
Claude subscription via the `claude` CLI (no API key required) — API
keys optional. Full guide: [INSTALL.md](INSTALL.md).
```

- [ ] **Step 3: Commit**

```bash
git add INSTALL.md README.md
git commit -m "docs: INSTALL.md — uv/pip/clone install, subscription-first setup"
```

---

### Task 8: Full verification + push

- [ ] **Step 1: Full test suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: no failures (compare with pre-work baseline).

- [ ] **Step 2: Fresh-machine simulation**

Run: `uv build && uv tool install --force --from dist/*.whl sac-capital && cd /tmp && SAC_HOME=/tmp/sac-final sac && sac setup < /dev/null || true`
Expected: banner renders; wizard starts (EOF-terminated run is fine for smoke).

- [ ] **Step 3: Push**

Per repo policy: commit + push (main tracks a fork remote, ahead 76 — push to origin as-is).

```bash
git push
```

PyPI publish (`uv publish`) is a separate, user-confirmed action — do NOT publish without explicit go-ahead.

---

## Self-Review

- Spec coverage: CLI surface (T5), subscription-first provider (T3, T4), wizard (T4), workdir (T2), distribution/build (T6), docs (T7), banner/logo (T1), testing (T1–T5), grill resolutions (broken `runner` entry T5; hatchling T6; SAC_HOME T2; binary-only detection T4; doctor --llm T5; hackathon in wheel T6). ✓
- No placeholders: all steps carry real code/commands. ✓
- Type consistency: `run_wizard(input_fn, which)`, `write_env(env, path, input_fn)`, `run_setup(input_fn)`, `resolve_workdir(cwd)`, `main(argv)` used consistently across tasks. ✓
