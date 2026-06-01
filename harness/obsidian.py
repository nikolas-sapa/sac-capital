from __future__ import annotations

from datetime import date
from pathlib import Path


class ObsidianVault:
    """Writes markdown files to the Obsidian vault for the polymarket-bot project."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def write_daily(self, log_date: date, content: str) -> Path:
        """Write the nightly consolidation log for `log_date`."""
        path = self._root / "daily" / f"{log_date.isoformat()}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def append_changelog(self, entry: str) -> None:
        """Append `entry` to params/CHANGELOG.md."""
        path = self._root / "params" / "CHANGELOG.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("# Parameter Changelog\n\n")
        with open(path, "a") as f:
            f.write(entry.rstrip("\n") + "\n")

    def write_proposal(self, slug: str, body: str) -> Path:
        """Create a proposal file awaiting human approval via Obsidian checkbox."""
        filename = f"{date.today().isoformat()}-{slug}.md"
        path = self._root / "proposals" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        proposal_body = body.rstrip("\n") + "\n\n- [ ] Approved\n"
        path.write_text(proposal_body)
        return path

    def update_index(self, stats: dict) -> None:
        """Rewrite index.md with the latest portfolio state."""
        path = self._root / "index.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# Polymarket Bot — Status ({date.today().isoformat()})\n"]
        for k, v in stats.items():
            lines.append(f"- **{k}**: {v}")
        path.write_text("\n".join(lines) + "\n")
