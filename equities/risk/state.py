"""Kernel state persistence: high-water mark and halt flag."""
import json
from pathlib import Path


def load_kernel_state(path: Path) -> dict:
    """Load persisted kernel state from JSON file.

    Args:
        path: Path to state file.

    Returns:
        dict with keys: high_water_mark (float), halted (bool), capital (float).
        Empty dict if file doesn't exist or is unreadable.
    """
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_kernel_state(path: Path, hwm: float, halted: bool, capital: float) -> None:
    """Persist kernel state to JSON file atomically.

    Args:
        path: Path to state file.
        hwm: High-water mark (peak equity).
        halted: Circuit-breaker flag.
        capital: Current capital (for validation on reload).
    """
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"high_water_mark": hwm, "halted": halted, "capital": capital}))
    tmp.replace(path)
