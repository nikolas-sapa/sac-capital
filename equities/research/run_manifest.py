from __future__ import annotations

from typing import Any

from hackathon.verifiability import Commitment, commitment_for_payload


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
