from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from harness.obsidian import ObsidianVault
    from harness.params import ParamStore


def classify_change(
    key: str,
    old: object,
    new: object,
    caps: dict[str, float],
) -> str:
    """Return "auto" or "approval" based on the magnitude of the change.

    caps maps parameter key → max delta for auto-apply.
    Changes beyond the cap, or for keys not in caps, require approval.
    """
    if key not in caps:
        return "approval"
    cap = caps[key]
    try:
        delta = abs(float(new) - float(old))
        return "auto" if delta <= cap else "approval"
    except (TypeError, ValueError):
        return "approval"


def apply_approved(vault: "ObsidianVault", store: "ParamStore") -> list[str]:
    """Scan the proposals folder for checked '- [x] Approved' lines and apply them.

    Proposal files must contain lines of the form:
        strategy: <name>
        key: <param_key>
        value: <json_value>
        reason: <optional reason>

    Returns a list of applied proposal slugs (file stems).
    """
    proposals_dir = vault._root / "proposals"
    if not proposals_dir.exists():
        return []

    applied: list[str] = []
    for path in sorted(proposals_dir.glob("*.md")):
        content = path.read_text()
        if "- [x] Approved" not in content:
            continue

        params: dict[str, str] = {}
        for line in content.splitlines():
            for field in ("strategy", "key", "value", "reason"):
                if line.startswith(f"{field}: "):
                    params[field] = line[len(field) + 2:].strip()

        if not all(f in params for f in ("strategy", "key", "value")):
            continue

        try:
            value = json.loads(params["value"])
        except json.JSONDecodeError:
            value = params["value"]

        store.set(
            params["strategy"],
            params["key"],
            value,
            reason=params.get("reason", "human-approved"),
            evidence="approved via Obsidian checkbox",
        )
        applied.append(path.stem)

    return applied
