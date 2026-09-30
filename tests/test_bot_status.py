from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

import runner_equities


def _settings(**overrides):
    values = {
        "bot_status_endpoint": "https://status.example/api/bot-status",
        "bot_status_write_token": "writer-secret",
        "bot_status_timeout_seconds": 1.25,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _event(**overrides):
    values = {
        "run_id": "20260930T100000Z",
        "run_type": "full_scan",
        "status": "running",
        "started_at": "2026-09-30T10:00:00Z",
        "updated_at": "2026-09-30T10:00:00Z",
    }
    values.update(overrides)
    return values


def test_publisher_posts_contract_auth_and_timeout():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert runner_equities._publish_bot_status(_settings(), _event(), post=client.post) is True

    assert len(requests) == 1
    request = requests[0]
    assert request.url == httpx.URL("https://status.example/api/bot-status")
    assert request.headers["Authorization"] == "Bearer writer-secret"
    assert request.extensions["timeout"]["read"] == 1.25
    assert request.read().decode() == (
        '{"run_id":"20260930T100000Z","run_type":"full_scan","status":"running",'
        '"started_at":"2026-09-30T10:00:00Z","updated_at":"2026-09-30T10:00:00Z"}'
    )


def test_endpoint_absence_disables_publisher():
    called = False

    def post(*args, **kwargs):
        nonlocal called
        called = True

    assert runner_equities._publish_bot_status(
        _settings(bot_status_endpoint=""), _event(), post=post
    ) is False
    assert called is False


@pytest.mark.parametrize(
    "error",
    [
        httpx.TimeoutException("timed out"),
        httpx.ConnectError("offline"),
    ],
)
def test_network_failures_are_isolated(error, capsys):
    def post(*args, **kwargs):
        raise error

    assert runner_equities._publish_bot_status(_settings(), _event(), post=post) is False
    assert "writer-secret" not in capsys.readouterr().out


def test_http_error_is_isolated():
    def post(*args, **kwargs):
        request = httpx.Request("POST", args[0])
        return httpx.Response(503, request=request)

    assert runner_equities._publish_bot_status(_settings(), _event(), post=post) is False


def test_success_lifecycle_emits_started_and_completed(monkeypatch):
    published: list[dict] = []
    moments = iter(
        [
            datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 30, 10, 5, tzinfo=timezone.utc),
        ]
    )
    monkeypatch.setattr(
        runner_equities,
        "_publish_bot_status",
        lambda settings, event: published.append(event.copy()) or True,
    )

    assert runner_equities._run_with_bot_status(lambda: "unchanged-result", _settings(), "full_scan", now=lambda: next(moments)) == "unchanged-result"
    assert [item["status"] for item in published] == ["running", "completed"]
    assert {item["run_type"] for item in published} == {"full_scan"}
    assert published[0]["run_id"] == "20260930T100000Z"
    assert published[1]["updated_at"] == "2026-09-30T10:05:00Z"


def test_failure_lifecycle_emits_failed_and_reraises(monkeypatch):
    published: list[dict] = []
    moments = iter(
        [
            datetime(2026, 9, 30, 11, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 30, 11, 1, tzinfo=timezone.utc),
        ]
    )
    monkeypatch.setattr(
        runner_equities,
        "_publish_bot_status",
        lambda settings, event: published.append(event.copy()) or True,
    )

    def fail():
        raise RuntimeError("runner failed")

    with pytest.raises(RuntimeError, match="runner failed"):
        runner_equities._run_with_bot_status(fail, _settings(), "routine", now=lambda: next(moments))

    assert [item["status"] for item in published] == ["running", "failed"]
    assert {item["run_type"] for item in published} == {"routine"}
    assert published[1]["started_at"] == published[0]["started_at"]


def test_publish_failure_does_not_change_action_result(monkeypatch):
    monkeypatch.setattr(runner_equities, "_publish_bot_status", lambda settings, event: False)
    fixed = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
    assert runner_equities._run_with_bot_status(
        lambda: 42, _settings(), "routine", now=lambda: fixed
    ) == 42


def test_preflight_failure_publishes_failed_status(monkeypatch, capsys):
    from scripts import preflight

    published: list[dict] = []
    monkeypatch.setattr(runner_equities, "load_config", lambda: _settings())
    monkeypatch.setattr(runner_equities.sys, "argv", ["runner_equities.py", "--mark-only"])
    monkeypatch.setattr(
        preflight,
        "run_preflight",
        lambda _settings: SimpleNamespace(ok=False, failures=["preflight issue"]),
    )
    monkeypatch.setattr(
        runner_equities,
        "_publish_bot_status",
        lambda _settings, event: published.append(event.copy()) or True,
    )

    with pytest.raises(SystemExit, match="1"):
        runner_equities.main()

    assert [item["status"] for item in published] == ["running", "failed"]
    assert {item["run_type"] for item in published} == {"routine"}
    assert "PREFLIGHT FAILED" in capsys.readouterr().out
