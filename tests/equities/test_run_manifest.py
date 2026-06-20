from __future__ import annotations

from core.config import Settings
from equities.research.run_manifest import build_run_manifest, settings_snapshot


def _base_kwargs() -> dict:
    return dict(
        config_snapshot={"max_position_pct": 0.05, "universe": "sp500"},
        prompt_versions_used=["thesis_miner_v3", "screen_v1"],
        model_ids=["claude-sonnet-4-6", "gpt-4o"],
        source_ids_fetched=["sec-filing-123", "news-456"],
        run_id="run-2026-06-20-001",
    )


def test_same_inputs_produce_same_hash() -> None:
    first = build_run_manifest(**_base_kwargs())
    second = build_run_manifest(**_base_kwargs())

    assert first.sha256 == second.sha256
    assert first.bytes32 == second.bytes32


def test_different_model_ids_change_hash() -> None:
    base = build_run_manifest(**_base_kwargs())

    kwargs = _base_kwargs()
    kwargs["model_ids"] = ["claude-sonnet-4-6", "gpt-4o-mini"]
    changed = build_run_manifest(**kwargs)

    assert base.sha256 != changed.sha256


def test_different_config_snapshot_changes_hash() -> None:
    base = build_run_manifest(**_base_kwargs())

    kwargs = _base_kwargs()
    kwargs["config_snapshot"] = {"max_position_pct": 0.10, "universe": "sp500"}
    changed = build_run_manifest(**kwargs)

    assert base.sha256 != changed.sha256


def test_bytes32_format_matches_commitment_convention() -> None:
    first = build_run_manifest(**_base_kwargs())

    assert first.bytes32.startswith("0x")
    assert len(first.bytes32) == 66


def test_kind_is_equity_run_manifest() -> None:
    manifest = build_run_manifest(**_base_kwargs())

    assert manifest.kind == "equity_run_manifest"


def test_list_order_is_significant_in_the_hash() -> None:
    """Document that list order in prompt_versions_used / model_ids /
    source_ids_fetched affects the hash. canonical_json sorts dict keys
    but does not reorder list contents, so callers are responsible for
    deciding/normalizing order if they want order-independence. This
    test pins down the current (order-sensitive) behavior."""

    kwargs = _base_kwargs()
    reordered = dict(kwargs)
    reordered["model_ids"] = list(reversed(kwargs["model_ids"]))

    original = build_run_manifest(**kwargs)
    swapped = build_run_manifest(**reordered)

    assert original.sha256 != swapped.sha256


def test_settings_snapshot_never_includes_secret_fields() -> None:
    settings = Settings(
        telegram_bot_token="secret-token",
        telegram_chat_id="secret-chat-id",
        anthropic_api_key="secret-anthropic-key",
        openai_api_key="secret-openai-key",
        finnhub_api_key="secret-finnhub-key",
        alpaca_api_key_id="secret-alpaca-key-id",
        alpaca_secret_key="secret-alpaca-secret",
    )

    snapshot = settings_snapshot(settings)

    for secret_field in (
        "telegram_bot_token",
        "telegram_chat_id",
        "anthropic_api_key",
        "openai_api_key",
        "finnhub_api_key",
        "alpaca_api_key_id",
        "alpaca_secret_key",
    ):
        assert secret_field not in snapshot
    for secret_value in (
        "secret-token",
        "secret-chat-id",
        "secret-anthropic-key",
        "secret-openai-key",
        "secret-finnhub-key",
        "secret-alpaca-key-id",
        "secret-alpaca-secret",
    ):
        assert secret_value not in snapshot.values()


def test_settings_snapshot_includes_behavioral_fields() -> None:
    snapshot = settings_snapshot(Settings())

    assert snapshot["max_position_pct"] == 0.02
    assert snapshot["live_trading_enabled"] is False
    assert snapshot["equity_max_positions"] == 4
