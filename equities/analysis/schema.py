from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


class AnalystOutputError(ValueError):
    """Raised when an LLM analyst response is not admissible as a recommendation."""


class AnalystDecision(BaseModel):
    action: Literal["buy", "reject"]
    reason: str = ""
    entry: float | None = Field(default=None, allow_inf_nan=False)
    stop_loss: float | None = Field(default=None, allow_inf_nan=False)
    take_profit: float | None = Field(default=None, allow_inf_nan=False)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    horizon: str = ""
    catalyst: str = ""
    thesis: str = ""
    business_quality: str = ""
    valuation: str = ""
    balance_sheet_risk: str = ""
    market_expectation_gap: str = ""
    invalidation: str = ""
    evidence_citations: list[str] = Field(default_factory=list)

    @field_validator(
        "reason",
        "horizon",
        "catalyst",
        "thesis",
        "business_quality",
        "valuation",
        "balance_sheet_risk",
        "market_expectation_gap",
        "invalidation",
        mode="before",
    )
    @classmethod
    def _coerce_text(cls, value: object) -> str:
        return "" if value is None else str(value).strip()

    @field_validator("evidence_citations", mode="before")
    @classmethod
    def _coerce_citations(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []

    @model_validator(mode="after")
    def _validate_buy(self) -> "AnalystDecision":
        if self.action == "reject":
            return self

        missing = [
            name
            for name in ("entry", "stop_loss", "take_profit", "confidence")
            if getattr(self, name) is None
        ]
        if missing:
            raise ValueError(f"buy_missing_fields={','.join(missing)}")

        assert self.entry is not None
        assert self.stop_loss is not None
        assert self.take_profit is not None
        if self.entry <= 0:
            raise ValueError("entry_must_be_positive")
        if self.stop_loss <= 0:
            raise ValueError("stop_loss_must_be_positive")
        if self.stop_loss >= self.entry:
            raise ValueError("stop_loss_must_be_below_entry")
        if self.take_profit <= self.entry:
            raise ValueError("take_profit_must_be_above_entry")
        if not self.catalyst:
            raise ValueError("catalyst_required")
        if not self.thesis:
            raise ValueError("thesis_required")
        required_memo = {
            "business_quality": self.business_quality,
            "valuation": self.valuation,
            "balance_sheet_risk": self.balance_sheet_risk,
            "market_expectation_gap": self.market_expectation_gap,
            "invalidation": self.invalidation,
        }
        missing_memo = [name for name, value in required_memo.items() if not value]
        if missing_memo:
            raise ValueError(f"memo_missing_fields={','.join(missing_memo)}")
        if not self.evidence_citations:
            raise ValueError("evidence_citations_required")
        return self

    def memo(self) -> dict[str, object]:
        return {
            "business_quality": self.business_quality,
            "valuation": self.valuation,
            "balance_sheet_risk": self.balance_sheet_risk,
            "market_expectation_gap": self.market_expectation_gap,
            "invalidation": self.invalidation,
            "evidence_citations": list(self.evidence_citations),
        }


def parse_analyst_decision(data: object) -> AnalystDecision:
    try:
        return AnalystDecision.model_validate(data)
    except ValidationError as exc:
        reasons = ";".join(err["msg"] for err in exc.errors())
        raise AnalystOutputError(reasons) from exc


def parse_analyst_decision_json(text: str) -> AnalystDecision:
    return parse_analyst_decision(_decode_json(text))


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = [line for line in lines[1:] if not line.startswith("```")]
        return "\n".join(inner)
    return text


def _decode_json(text: str) -> object:
    try:
        return json.loads(_strip_fences(text))
    except json.JSONDecodeError as exc:
        raise AnalystOutputError(f"invalid_json:{exc.msg}") from exc


class PrefilterRanking(BaseModel):
    ticker: str
    score: int = Field(ge=0, le=10)
    reason: str = ""

    @field_validator("ticker", "reason", mode="before")
    @classmethod
    def _coerce_text(cls, value: object) -> str:
        return "" if value is None else str(value).strip()


class PrefilterDecision(BaseModel):
    rankings: list[PrefilterRanking] = Field(default_factory=list)


class ChallengerDecision(BaseModel):
    verdict: Literal["pass", "weaken", "reject"] = "pass"
    objections: list[str] = Field(default_factory=list)
    confidence_adjustment: float = Field(default=0.0, ge=-1.0, le=0.0)
    size_verdict: Literal["full", "half", "skip"] = "full"
    size_rationale: str = ""

    @field_validator("objections", mode="before")
    @classmethod
    def _coerce_objections(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []

    @field_validator("size_verdict", mode="before")
    @classmethod
    def _coerce_size_verdict(cls, value: object) -> str:
        if value is None:
            return "full"
        text = str(value).strip().lower()
        if text in {"full", "half", "skip"}:
            return text
        return "full"  # Invalid → default to full for backward compat

    @field_validator("size_rationale", mode="before")
    @classmethod
    def _coerce_size_rationale(cls, value: object) -> str:
        return "" if value is None else str(value).strip()

    @model_validator(mode="after")
    def _validate_weaken(self) -> "ChallengerDecision":
        if self.verdict == "weaken" and self.confidence_adjustment >= 0:
            raise ValueError("weaken_requires_negative_confidence_adjustment")
        return self


class AuditorDecision(BaseModel):
    verdict: Literal["pass", "reject"] = "pass"
    consistency_penalty: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""

    @field_validator("verdict", mode="before")
    @classmethod
    def _coerce_verdict(cls, value: object) -> str:
        text = "" if value is None else str(value).strip().lower()
        return "pass" if text == "proceed" else text

    @field_validator("reason", mode="before")
    @classmethod
    def _coerce_reason(cls, value: object) -> str:
        return "" if value is None else str(value).strip()


class CoreDCADecision(BaseModel):
    action: Literal["dca", "wait"]
    reason: str = ""
    dca_pct: float | None = Field(default=None, ge=0.0)
    thesis: str = ""

    @field_validator("reason", "thesis", mode="before")
    @classmethod
    def _coerce_text(cls, value: object) -> str:
        return "" if value is None else str(value).strip()

    @model_validator(mode="after")
    def _validate_dca(self) -> "CoreDCADecision":
        if self.action == "dca":
            if self.dca_pct is None:
                raise ValueError("dca_pct_required")
            if not self.thesis:
                raise ValueError("thesis_required")
        return self


def _validation_error(exc: ValidationError) -> AnalystOutputError:
    reasons = ";".join(err["msg"] for err in exc.errors())
    return AnalystOutputError(reasons)


def parse_prefilter_decision(text: str) -> PrefilterDecision:
    try:
        return PrefilterDecision.model_validate(_decode_json(text))
    except ValidationError as exc:
        raise _validation_error(exc) from exc


def parse_challenger_decision(text: str) -> ChallengerDecision:
    try:
        return ChallengerDecision.model_validate(_decode_json(text))
    except ValidationError as exc:
        raise _validation_error(exc) from exc


def parse_auditor_decision(text: str) -> AuditorDecision:
    try:
        return AuditorDecision.model_validate(_decode_json(text))
    except ValidationError as exc:
        raise _validation_error(exc) from exc


def parse_core_dca_decision(text: str) -> CoreDCADecision:
    try:
        return CoreDCADecision.model_validate(_decode_json(text))
    except ValidationError as exc:
        raise _validation_error(exc) from exc
