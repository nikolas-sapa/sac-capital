from __future__ import annotations

import sys
import time
import types
from types import SimpleNamespace

import pytest


def test_reconcile_only_cli_calls_reconcile_hook(monkeypatch):
    import runner_equities

    calls: list[str] = []

    async def fake_reconcile_only() -> None:
        calls.append("reconcile")

    async def fail_run_once(*args, **kwargs) -> None:
        raise AssertionError("run_once should not run in reconcile-only mode")

    monkeypatch.setattr(sys, "argv", ["runner_equities.py", "--reconcile-only"])
    monkeypatch.setattr(runner_equities, "run_reconcile_only", fake_reconcile_only)
    monkeypatch.setattr(runner_equities, "run_once", fail_run_once)

    runner_equities.main()

    assert calls == ["reconcile"]


def test_active_broker_order_helper_blocks_duplicate_active_statuses():
    import runner_equities

    assert runner_equities._has_active_broker_order(None) is False
    assert runner_equities._has_active_broker_order({"status": "submitted"}) is True
    assert runner_equities._has_active_broker_order({"status": "partially_filled"}) is True
    assert runner_equities._has_active_broker_order({"status": "open"}) is True
    assert runner_equities._has_active_broker_order({"status": "rejected"}) is False
    assert runner_equities._has_active_broker_order({"status": "canceled"}) is False


def test_llm_failure_budget_trips_cleanly():
    import runner_equities

    class FailingLLM:
        def complete(self, system: str, user: str, model: str):
            raise RuntimeError("llm down")

    stats = runner_equities.RunStats(
        started_monotonic=time.monotonic(),
        max_runtime_seconds=60,
        max_provider_failures=20,
        max_llm_failures=0,
    )
    client = runner_equities._LLMFailureCountingClient(FailingLLM(), stats)

    with pytest.raises(runner_equities.LLMFailureBudgetExceeded):
        client.complete("system", "user", "model-x")

    assert stats.llm_failures == 1
    assert stats.exit_reason == "max_llm_failures_exceeded"


def test_news_provider_failure_logs_counts_and_continues(capsys):
    from equities.data.news_composite import CompositeNewsProvider

    class FailingNews:
        def headlines(self, ticker: str, limit: int = 15) -> list[str]:
            raise TimeoutError("slow provider")

    class WorkingNews:
        def headlines(self, ticker: str, limit: int = 15) -> list[str]:
            return ["headline"]

    failures = 0

    def record_failure() -> None:
        nonlocal failures
        failures += 1

    provider = CompositeNewsProvider(
        [FailingNews(), WorkingNews()],
        failure_callback=record_failure,
    )

    assert provider.headlines("MSFT") == ["headline"]
    assert failures == 1
    assert "source=FailingNews ticker=MSFT error=slow provider" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("argv", "expected_no_analyse", "expected_mark_only", "expected_dry_run"),
    [
        (["runner_equities.py"], False, False, False),
        (["runner_equities.py", "--no-analyse"], True, False, False),
        (["runner_equities.py", "--mark-only"], False, True, False),
        (["runner_equities.py", "--dry-run"], False, False, True),
    ],
)
def test_existing_cli_modes_still_call_run_once(
    monkeypatch,
    argv,
    expected_no_analyse,
    expected_mark_only,
    expected_dry_run,
):
    import runner_equities

    calls: list[dict[str, bool]] = []

    async def fake_run_once(
        swing_universe,
        core_universe,
        no_analyse=False,
        mark_only=False,
        dry_run=False,
    ) -> None:
        calls.append({
            "no_analyse": no_analyse,
            "mark_only": mark_only,
            "dry_run": dry_run,
        })

    async def fail_reconcile_only() -> None:
        raise AssertionError("run_reconcile_only should not run in normal modes")

    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(runner_equities, "run_once", fake_run_once)
    monkeypatch.setattr(runner_equities, "run_reconcile_only", fail_reconcile_only)

    runner_equities.main()

    assert calls == [{
        "no_analyse": expected_no_analyse,
        "mark_only": expected_mark_only,
        "dry_run": expected_dry_run,
    }]


@pytest.mark.asyncio
async def test_run_reconcile_only_uses_available_reconciler(monkeypatch):
    import runner_equities

    settings = SimpleNamespace(name="settings")
    seen: list[object] = []
    module = types.ModuleType("equities.execution.reconciler")

    async def reconcile_alpaca(received_settings) -> None:
        seen.append(received_settings)

    module.reconcile_alpaca = reconcile_alpaca

    monkeypatch.setitem(sys.modules, "equities.execution.reconciler", module)
    monkeypatch.setattr(runner_equities, "load_config", lambda: settings)

    await runner_equities.run_reconcile_only()

    assert seen == [settings]
