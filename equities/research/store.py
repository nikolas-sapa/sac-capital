from __future__ import annotations

import json
from pathlib import Path

from equities.research.artifacts import EquityResearchArtifact


class ResearchArtifactStore:
    """Append-only JSONL store for auditable equity research artifacts."""

    def __init__(self, path: str | Path = "data/research_artifacts.jsonl") -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, artifact: EquityResearchArtifact) -> None:
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(artifact.model_dump_json() + "\n")

    def read_all(self) -> list[EquityResearchArtifact]:
        if not self._path.exists():
            return []
        artifacts: list[EquityResearchArtifact] = []
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    artifacts.append(EquityResearchArtifact.model_validate(json.loads(line)))
        return artifacts
