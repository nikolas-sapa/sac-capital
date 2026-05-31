"""Shared helpers for parsing gamma API JSON responses."""
from __future__ import annotations

from typing import Any


def maybe_parse_json_field(value: Any) -> list:
    """Return *value* as a list.

    The gamma API sometimes encodes list fields as JSON strings (e.g.
    ``"[\\"Yes\\", \\"No\\"]"``).  Handle both cases defensively.
    Also returns [] for None input.
    """
    import json

    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
        raise ValueError(f"Expected JSON array string, got: {value!r}")
    raise TypeError(f"Cannot coerce {type(value)} to list")
