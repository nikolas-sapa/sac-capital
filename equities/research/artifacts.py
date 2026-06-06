from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SourceRef(BaseModel):
    id: str
    kind: Literal["news", "filing", "fundamental", "price", "candidate", "other"]
    source: str
    url_or_id: str = ""
    title: str = ""
    published_at: str = ""
    fetched_at: str = Field(default_factory=utc_now_iso)
    content_hash: str = ""


class Citation(BaseModel):
    source_ref_id: str
    quote_or_summary: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ExtractionRef(BaseModel):
    provider: str
    raw_hash: str
    content_hash: str
    fetched_at: str = Field(default_factory=utc_now_iso)


class EquityResearchArtifact(BaseModel):
    artifact_id: str
    as_of: str = Field(default_factory=utc_now_iso)
    ticker: str
    candidate: dict[str, Any]
    sources: list[SourceRef] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    extractions: list[ExtractionRef] = Field(default_factory=list)
    llm_model: str = ""
    prompt_hash: str = ""
    prompt_version: str = "equity_analyst_v1"
    output_json: dict[str, Any] | None = None
    raw_output: str = ""
    confidence: float | None = None
    decision: Literal["approved", "rejected", "error"]
    rejection_reason: str = ""
