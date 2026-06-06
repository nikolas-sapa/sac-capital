from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from equities.research.artifacts import stable_hash


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def checkpoint_key(
    *,
    run_date: str,
    ticker: str,
    stage: str,
    prompt_hash: str,
    model: str,
) -> str:
    return stable_hash({
        "run_date": run_date,
        "ticker": ticker.upper(),
        "stage": stage,
        "prompt_hash": prompt_hash,
        "model": model,
    })


@dataclass(frozen=True)
class AnalysisCheckpoint:
    key: str
    ticker: str
    stage: str
    model: str
    prompt_hash: str
    raw_output: str
    parsed_output: dict[str, Any]
    cost_usd: float
    created_at: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "key": self.key,
                "ticker": self.ticker,
                "stage": self.stage,
                "model": self.model,
                "prompt_hash": self.prompt_hash,
                "raw_output": self.raw_output,
                "parsed_output": self.parsed_output,
                "cost_usd": self.cost_usd,
                "created_at": self.created_at,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnalysisCheckpoint":
        parsed = data.get("parsed_output")
        if not isinstance(parsed, dict):
            raise ValueError("checkpoint_parsed_output_not_dict")
        return cls(
            key=str(data["key"]),
            ticker=str(data["ticker"]),
            stage=str(data["stage"]),
            model=str(data["model"]),
            prompt_hash=str(data["prompt_hash"]),
            raw_output=str(data.get("raw_output", "")),
            parsed_output=parsed,
            cost_usd=float(data.get("cost_usd", 0.0)),
            created_at=str(data.get("created_at", "")),
        )


class AnalysisCheckpointStore:
    def __init__(self, path: str | Path = "data/equity_analysis_checkpoints.jsonl") -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def get(self, key: str) -> AnalysisCheckpoint | None:
        latest: AnalysisCheckpoint | None = None
        for checkpoint in self._read_all_safe():
            if checkpoint.key == key:
                latest = checkpoint
        return latest

    def put(self, checkpoint: AnalysisCheckpoint) -> None:
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(checkpoint.to_json() + "\n")

    def clear_for_ticker(self, ticker: str) -> int:
        ticker = ticker.upper()
        checkpoints = self._read_all_safe()
        kept = [checkpoint for checkpoint in checkpoints if checkpoint.ticker.upper() != ticker]
        removed = len(checkpoints) - len(kept)
        self._rewrite(kept)
        return removed

    def clear_all(self) -> int:
        checkpoints = self._read_all_safe()
        self._rewrite([])
        return len(checkpoints)

    def _read_all_safe(self) -> list[AnalysisCheckpoint]:
        if not self._path.exists():
            return []
        checkpoints: list[AnalysisCheckpoint] = []
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    checkpoints.append(AnalysisCheckpoint.from_dict(json.loads(line)))
                except Exception:
                    continue
        return checkpoints

    def _rewrite(self, checkpoints: list[AnalysisCheckpoint]) -> None:
        if not checkpoints:
            self._path.write_text("", encoding="utf-8")
            return
        with self._path.open("w", encoding="utf-8") as handle:
            for checkpoint in checkpoints:
                handle.write(checkpoint.to_json() + "\n")
