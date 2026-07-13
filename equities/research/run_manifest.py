from __future__ import annotations

from typing import Any

from core.config import Settings
from hackathon.verifiability import Commitment, commitment_for_payload

# Behavioral/risk knobs only — never a credential, token, or secret field.
# config_snapshot is hashed and written to disk (data/run_manifests.jsonl) in
# plaintext as part of the Commitment payload, so anything not on this
# allowlist must never reach settings_snapshot()'s output.
_SAFE_CONFIG_FIELDS = (
    "llm_provider",
    "execution_provider",
    "bankroll_usd",
    "kelly_fraction",
    "max_position_pct",
    "research_probe_pct",
    "core_dca_pct",
    "max_order_usd",
    "max_daily_order_count",
    "allow_extended_hours",
    "allow_test_orders",
    "live_trading_enabled",
    "equity_risk_pct",
    "equity_max_positions",
    "equity_max_name_pct",
    "equity_max_sector_pct",
    "equity_daily_loss_limit_pct",
    "equity_drawdown_limit_pct",
    "equity_max_price_age_days",
    "equity_provider_timeout_seconds",
    "equity_provider_retries",
    "equity_runner_max_runtime_seconds",
    "equity_runner_max_provider_failures",
    "equity_runner_max_llm_failures",
    "equity_runner_dry_run",
    "equity_min_rr",
    "equity_hard_tech_gate",
    "equity_trail_r",
    "equity_kelly_min_trades",
    "equity_pyramid_enabled",
    "alpaca_paper",
    "anthropic_fast_model",
    "anthropic_strong_model",
    "openai_fast_model",
    "openai_strong_model",
    "codex_fast_model",
    "codex_strong_model",
)


def settings_snapshot(settings: Settings) -> dict[str, Any]:
    """Redact *settings* down to the allowlisted behavioral fields.

    Excludes every credential/token field (api keys, secret keys, telegram
    chat id, alpaca base url is fine but kept out for now since it's not on
    the allowlist) so a config_snapshot is always safe to hash and persist
    in plaintext via build_run_manifest().
    """
    return {field: getattr(settings, field) for field in _SAFE_CONFIG_FIELDS}


def build_run_manifest(
    config_snapshot: dict[str, Any],
    prompt_versions_used: list[str],
    model_ids: list[str],
    source_ids_fetched: list[str],
    *,
    run_id: str | None = None,
) -> Commitment:
    """Build a single tamper-evident commitment for one bot run.

    Ties together the config snapshot, prompt versions, model ids, and
    full source set used during a run, hashed deterministically via the
    same `Commitment` primitive used for per-decision/per-artifact
    provenance (see hackathon.verifiability).

    Determinism: identical inputs always produce the identical hash.
    List order in `prompt_versions_used`, `model_ids`, and
    `source_ids_fetched` is significant — `canonical_json` only sorts
    dict keys, it does not reorder list contents. Callers that want
    order-independent hashing must sort their lists before calling this
    function; this function does not sort them implicitly so that
    callers who *do* care about fetch/usage order (e.g. for audit
    sequencing) are not silently misrepresented.

    `run_id`, if provided, is included in the hashed payload as an
    explicit, caller-supplied identifier — never generated internally
    (e.g. no `uuid4()`/`datetime.now()`), so the manifest hash stays a
    pure function of its inputs.
    """

    payload = {
        "run_id": run_id,
        "config_snapshot": config_snapshot,
        "prompt_versions_used": prompt_versions_used,
        "model_ids": model_ids,
        "source_ids_fetched": source_ids_fetched,
    }
    return commitment_for_payload(
        kind="equity_run_manifest",
        source="equities.research.run_manifest",
        payload=payload,
    )
