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


def risk_decision_artifact(
    recommendation: Any,
    *,
    decision: Literal["approved", "rejected"],
    rejection_reason: str = "",
    stage: str = "risk",
    shares: float | None = None,
    notional: float | None = None,
    risk_metrics: dict[str, Any] | None = None,
    data_cutoff_utc: str | None = None,
) -> EquityResearchArtifact:
    """Build a decision artifact for the risk/execution stage of the runner.

    Captures *why a recommendation was traded or skipped* after analyst approval —
    the kernel/notional/daily-cap/broker rejections that previously only printed.
    Feeds the self-improvement harness and the on-chain commitment exporter.
    """
    inst = recommendation.instrument
    ticker = inst.ticker
    candidate_payload: dict[str, Any] = {
        "ticker": ticker,
        "sleeve": recommendation.sleeve.value,
        "side": recommendation.side,
        "entry": recommendation.entry,
        "stop_loss": recommendation.stop_loss,
        "take_profit": recommendation.take_profit,
        "size_pct": recommendation.size_pct,
        "catalyst": recommendation.catalyst,
        "horizon": recommendation.horizon,
    }
    output_json: dict[str, Any] = {
        "stage": stage,
        "decision": decision,
        "rejection_reason": rejection_reason,
        "thesis": recommendation.thesis,
        "shares": shares,
        "notional": notional,
        "risk_metrics": risk_metrics or {},
        "data_cutoff_utc": data_cutoff_utc,
    }
    return EquityResearchArtifact(
        artifact_id=stable_hash({
            "ticker": ticker,
            "candidate": candidate_payload,
            "stage": stage,
            "decision": decision,
            "rejection_reason": rejection_reason,
            "shares": shares,
        }),
        ticker=ticker,
        candidate=candidate_payload,
        llm_model="",
        prompt_version=f"risk_stage_{stage}_v1",
        output_json=output_json,
        confidence=recommendation.confidence,
        decision=decision,
        rejection_reason=rejection_reason,
    )


def static_research_decision_artifact(row: dict[str, Any]) -> EquityResearchArtifact:
    """Build an approved artifact from a research_static ledger row.

    Static supply-chain probes can bypass the LLM analyst but still encode a
    thesis and realized outcome. Persisting them lets decision memory learn
    from the same winner pattern as normal analyst approvals.
    """
    ticker = str(row.get("ticker", "")).upper()
    output_json = {
        "action": "buy",
        "entry": row.get("entry_price"),
        "stop_loss": row.get("stop_loss"),
        "take_profit": row.get("take_profit"),
        "confidence": row.get("confidence"),
        "catalyst": "static supply-chain discovery lag",
        "thesis": row.get("thesis", ""),
        "horizon": "1-4 weeks",
        "exit_price": row.get("exit_price"),
        "exit_reason": row.get("exit_reason"),
        "realized_pnl": row.get("realized_pnl"),
        "closed_at": row.get("closed_at"),
        "source": "equity_ledger",
    }
    candidate = {
        "ticker": ticker,
        "strategy": row.get("strategy", "research_static"),
        "entry": row.get("entry_price"),
        "opened_at": row.get("opened_at"),
        "evidence": row.get("thesis", ""),
    }
    return EquityResearchArtifact(
        artifact_id=stable_hash({
            "ticker": ticker,
            "strategy": row.get("strategy", "research_static"),
            "opened_at": row.get("opened_at"),
            "entry": row.get("entry_price"),
        }),
        as_of=str(row.get("opened_at") or utc_now_iso()),
        ticker=ticker,
        candidate=candidate,
        llm_model="",
        prompt_version="research_static_ledger_v1",
        output_json=output_json,
        raw_output="",
        confidence=row.get("confidence"),
        decision="approved",
        rejection_reason="",
    )
