"""07c — Three-stage equity analyst: Haiku prefilter → Sonnet thesis → Sonnet challenger.

Stage 1 (Haiku):      Score all candidates cheaply, keep top `max_candidates`.
Stage 2 (Sonnet):     For each survivor, write bull thesis + entry/stop/TP.
Stage 3 (Sonnet):     Challenger argues against the bull case; can reject or weaken.

Daily budget guard prevents runaway spend. When the budget is exhausted,
remaining candidates are skipped for the day.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Protocol

from core.assets.instrument import Instrument
from equities.analysis.budget import DailyBudget
from equities.analysis.prompt import (
    _ANALYST_SYSTEM,
    _AUDITOR_SYSTEM,
    _CHALLENGER_SYSTEM,
    _PREFILTER_SYSTEM,
    build_analyst_prompt,
    build_auditor_prompt,
    build_challenger_prompt,
    build_prefilter_prompt,
)
from equities.analysis.schema import (
    AnalystOutputError,
    parse_analyst_decision_json,
    parse_auditor_decision,
    parse_challenger_decision,
    parse_prefilter_decision,
)
from equities.data.fundamentals import FundamentalsProvider
from equities.research.artifacts import (
    EquityResearchArtifact,
    ExtractionRef,
    SourceRef,
    stable_hash,
)
from equities.research.store import ResearchArtifactStore
from equities.screen.event_screen import CandidateEvent
from equities.strategy import Recommendation, Sleeve

# ---------------------------------------------------------------------------
# LLM client protocol (injectable for testing)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int

    def cost_usd(self, model: str = "sonnet") -> float:
        if "haiku" in model:
            return self.input_tokens * 8e-7 + self.output_tokens * 4e-6
        return self.input_tokens * 3e-6 + self.output_tokens * 1.5e-5


class LLMClient(Protocol):
    def complete(self, system: str, user: str, model: str) -> LLMResponse: ...


class LLMFailureBudgetExceeded(RuntimeError):
    """Raised when the runner-level LLM failure fuse trips."""


class AnthropicLLMClient:
    """Real Anthropic SDK client. Requires ANTHROPIC_API_KEY in env."""

    def __init__(self, api_key: str) -> None:
        from anthropic import Anthropic
        self._client = Anthropic(api_key=api_key)

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        resp = self._client.messages.create(
            model=model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = resp.content[0].text if resp.content else ""
        return LLMResponse(
            content=text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )


# ---------------------------------------------------------------------------
# Data providers (injected — real implementations in equities/data/)
# ---------------------------------------------------------------------------

class PriceProvider(Protocol):
    def latest_close(self, ticker: str) -> float | None: ...


class NewsProvider(Protocol):
    def headlines(self, ticker: str, limit: int = 15) -> list[str]: ...


class FilingsSummaryProvider(Protocol):
    def summary(self, ticker: str, days: int = 90) -> list[str]: ...


# ---------------------------------------------------------------------------
# Analyst
# ---------------------------------------------------------------------------

_HAIKU = "claude-haiku-4-5-20251001"
_SONNET = "claude-sonnet-4-6"
_HAIKU_COST_PER_CANDIDATE = 0.0005
_SONNET_COST_PER_CANDIDATE = 0.01
_CHALLENGER_COST = 0.008
_AUDITOR_COST = 0.006


class EquityAnalyst:
    """Three-stage equity analyst: prefilter → bull thesis → challenger.

    Stage 1: Haiku scores all candidates and returns top `max_candidates`.
    Stage 2: Sonnet writes entry/stop/TP for each surviving candidate.
    Stage 3: Sonnet challenger argues against the bull case.
              - "reject" → drop the trade
              - "weaken" → reduce confidence by objection delta
              - "pass"   → keep as-is

    When `llm` is None, uses the default LLM client: OpenAI if OPENAI_API_KEY
    is set, otherwise Claude CLI fallback.
    """

    def __init__(
        self,
        llm: LLMClient | None = None,
        prices: PriceProvider | None = None,
        news: NewsProvider | None = None,
        filings: FilingsSummaryProvider | None = None,
        fundamentals: FundamentalsProvider | None = None,
        budget: DailyBudget | None = None,
        max_candidates: int = 5,
        max_price_age_days: int = 7,
        artifact_store: ResearchArtifactStore | None = None,
    ) -> None:
        if llm is None:
            from core.claude_client import ClaudeCodeClient
            llm = ClaudeCodeClient()  # type: ignore[assignment]
        self._llm = llm
        self._prices = prices
        self._news = news
        self._filings = filings
        self._fundamentals = fundamentals
        self._budget = budget or DailyBudget(daily_limit_usd=1.0)
        self._max_candidates = max_candidates
        self._max_price_age_days = max_price_age_days
        self._artifact_store = artifact_store
        self._candidate_by_ticker: dict[str, CandidateEvent] = {}

    def analyse(
        self,
        candidates: list[CandidateEvent],
        regime: str = "neutral",
        vix: float | None = None,
        yield_curve: float | None = None,
    ) -> list[Recommendation]:
        """Run the three-stage pipeline. Returns Recommendations."""
        if not candidates:
            return []

        self._candidate_by_ticker = {c.instrument.ticker: c for c in candidates}
        survivors = self._prefilter(candidates)

        results: list[Recommendation] = []
        for candidate in survivors:
            if not self._budget.allow(_SONNET_COST_PER_CANDIDATE + _CHALLENGER_COST):
                break
            rec = self._analyse_one(candidate, regime=regime, vix=vix, yield_curve=yield_curve)
            if rec is None:
                continue
            challenged, objections = self._challenge(rec)
            if challenged is None:
                continue
            audited = self._audit(challenged, objections)
            if audited is None:
                continue
            _action, size_pct = _compute_build_action(
                analyst_confidence=audited.confidence,
                consistency_penalty=0.0,  # already applied by auditor
                regime=regime,
            )
            if size_pct == 0.0:
                continue  # WAIT — skip
            final = Recommendation(
                instrument=audited.instrument,
                sleeve=audited.sleeve,
                side=audited.side,
                entry=audited.entry,
                stop_loss=audited.stop_loss,
                take_profit=audited.take_profit,
                size_pct=size_pct,
                confidence=audited.confidence,
                catalyst=audited.catalyst,
                thesis=audited.thesis,
                horizon=audited.horizon,
                memo=audited.memo,
            )
            self._record_recommendation_artifact(
                final,
                stage="final",
                llm_model="",
                prompt="",
                raw_output="",
                output_json=_recommendation_json(final),
                decision="approved",
                rejection_reason="",
            )
            results.append(final)

        return results

    def _prefilter(self, candidates: list[CandidateEvent]) -> list[CandidateEvent]:
        if not self._budget.allow(_HAIKU_COST_PER_CANDIDATE):
            return candidates[: self._max_candidates]

        user_msg = build_prefilter_prompt(candidates)
        try:
            resp = self._llm.complete(_PREFILTER_SYSTEM, user_msg, _HAIKU)
            self._budget.record(resp.cost_usd("haiku"))
            parsed = parse_prefilter_decision(resp.content)
            scores: dict[str, int] = {r.ticker: r.score for r in parsed.rankings}
            ranked = sorted(candidates, key=lambda c: scores.get(c.instrument.ticker, 0), reverse=True)
            return ranked[: self._max_candidates]
        except LLMFailureBudgetExceeded:
            raise
        except Exception:
            return candidates[: self._max_candidates]

    def _analyse_one(
        self,
        candidate: CandidateEvent,
        regime: str = "neutral",
        vix: float | None = None,
        yield_curve: float | None = None,
    ) -> Recommendation | None:
        ticker = candidate.instrument.ticker
        price = self._validated_price(ticker)
        if price is None:
            self._record_artifact(
                candidate,
                price=None,
                news=[],
                filings=[],
                sector="",
                analyst_count=0,
                llm_model=_SONNET,
                prompt="",
                raw_output="",
                output_json=None,
                decision="rejected",
                rejection_reason="invalid_or_stale_price",
            )
            return None
        headlines = self._news.headlines(ticker, limit=15)
        filings = self._filings.summary(ticker, days=90)

        sector = ""
        analyst_count = 0
        if self._fundamentals:
            try:
                snap = self._fundamentals.fetch(ticker)
                sector = snap.sector
                analyst_count = snap.analyst_count
            except Exception:
                pass

        user_msg = build_analyst_prompt(
            candidate=candidate,
            current_price=price,
            news=headlines,
            filings=filings,
            sector=sector,
            analyst_count=analyst_count,
            macro_regime=regime,
            vix=vix,
            yield_curve=yield_curve,
        )
        try:
            resp = self._llm.complete(_ANALYST_SYSTEM, user_msg, _SONNET)
            self._budget.record(resp.cost_usd("sonnet"))
            data = parse_analyst_decision_json(resp.content)
        except AnalystOutputError as exc:
            print(f"  REJECTED [{ticker}] analyst_output_invalid: {exc}")
            self._record_artifact(
                candidate,
                price=price,
                news=headlines,
                filings=filings,
                sector=sector,
                analyst_count=analyst_count,
                llm_model=_SONNET,
                prompt=user_msg,
                raw_output=resp.content if "resp" in locals() else "",
                output_json=raw_data if "raw_data" in locals() else None,
                decision="rejected",
                rejection_reason=f"analyst_output_invalid:{exc}",
            )
            return None
        except LLMFailureBudgetExceeded:
            raise
        except Exception as exc:
            self._record_artifact(
                candidate,
                price=price,
                news=headlines,
                filings=filings,
                sector=sector,
                analyst_count=analyst_count,
                llm_model=_SONNET,
                prompt=user_msg,
                raw_output=resp.content if "resp" in locals() else "",
                output_json=raw_data if "raw_data" in locals() else None,
                decision="error",
                rejection_reason=f"analyst_exception:{exc}",
            )
            return None

        if data.action != "buy":
            self._record_artifact(
                candidate,
                price=price,
                news=headlines,
                filings=filings,
                sector=sector,
                analyst_count=analyst_count,
                llm_model=_SONNET,
                prompt=user_msg,
                raw_output=resp.content,
                output_json=data.model_dump(),
                decision="rejected",
                rejection_reason=data.reason or "llm_reject",
            )
            return None

        self._record_artifact(
            candidate,
            price=price,
            news=headlines,
            filings=filings,
            sector=sector,
            analyst_count=analyst_count,
            llm_model=_SONNET,
            prompt=user_msg,
            raw_output=resp.content,
            output_json=data.model_dump(),
            decision="approved",
            rejection_reason="",
        )
        return Recommendation(
            instrument=candidate.instrument,
            sleeve=Sleeve.SWING,
            side="buy",
            entry=float(data.entry),
            stop_loss=float(data.stop_loss),
            take_profit=float(data.take_profit),
            size_pct=0.02,
            confidence=float(data.confidence),
            catalyst=data.catalyst,
            thesis=data.thesis,
            horizon=data.horizon or "1-2 weeks",
            memo=data.memo(),
        )

    def _validated_price(self, ticker: str) -> float | None:
        if self._prices is None:
            print(f"  REJECTED [{ticker}] market_data_missing: no_price_provider")
            return None

        price = self._prices.latest_close(ticker)
        if price is None:
            print(f"  REJECTED [{ticker}] market_data_missing: latest_close_none")
            return None
        if not math.isfinite(price) or price <= 0:
            print(f"  REJECTED [{ticker}] market_data_invalid: latest_close={price!r}")
            return None

        latest_bar = getattr(self._prices, "latest_bar", None)
        if callable(latest_bar):
            try:
                bar = latest_bar(ticker)
            except Exception as exc:
                print(f"  REJECTED [{ticker}] market_data_error: latest_bar_failed={exc}")
                return None
            bar_day = getattr(bar, "day", None)
            if bar_day is None:
                print(f"  REJECTED [{ticker}] market_data_missing: latest_bar_day_none")
                return None
            if isinstance(bar_day, datetime):
                bar_date = bar_day.date()
            elif isinstance(bar_day, date):
                bar_date = bar_day
            else:
                print(f"  REJECTED [{ticker}] market_data_invalid: latest_bar_day={bar_day!r}")
                return None
            age_days = (datetime.now(tz=timezone.utc).date() - bar_date).days
            if age_days > self._max_price_age_days:
                print(
                    f"  REJECTED [{ticker}] market_data_stale: "
                    f"latest_bar={bar_date.isoformat()} age_days={age_days}"
                )
                return None

        return price

    def _record_artifact(
        self,
        candidate: CandidateEvent,
        *,
        price: float | None,
        news: list[str],
        filings: list[str],
        sector: str,
        analyst_count: int,
        llm_model: str,
        prompt: str,
        raw_output: str,
        output_json: dict[str, Any] | None,
        decision: str,
        rejection_reason: str,
        stage: str = "analyst",
    ) -> None:
        if self._artifact_store is None:
            return

        ticker = candidate.instrument.ticker
        candidate_payload = {
            "ticker": ticker,
            "event_type": candidate.event_type.value,
            "evidence": candidate.evidence,
            "urgency": candidate.urgency,
            "days_to_event": candidate.days_to_event,
            "sector": sector,
            "analyst_count": analyst_count,
            "current_price": price,
        }
        sources: list[SourceRef] = [
            SourceRef(
                id=f"{ticker}:candidate",
                kind="candidate",
                source="event_screen",
                title=candidate.evidence,
                content_hash=stable_hash(candidate_payload),
            )
        ]
        if price is not None:
            sources.append(
                SourceRef(
                    id=f"{ticker}:price",
                    kind="price",
                    source="price_provider",
                    title=f"latest_close={price}",
                    content_hash=stable_hash({"ticker": ticker, "price": price}),
                )
            )
        for idx, headline in enumerate(news[:15]):
            sources.append(
                SourceRef(
                    id=f"{ticker}:news:{idx}",
                    kind="news",
                    source="news_provider",
                    title=headline,
                    content_hash=stable_hash(headline),
                )
            )
        for idx, filing in enumerate(filings[:10]):
            sources.append(
                SourceRef(
                    id=f"{ticker}:filing:{idx}",
                    kind="filing",
                    source="filings_provider",
                    title=filing,
                    content_hash=stable_hash(filing),
                )
            )

        raw_hash = stable_hash(raw_output)
        artifact = EquityResearchArtifact(
            artifact_id=stable_hash({
                "ticker": ticker,
                "candidate": candidate_payload,
                "prompt": prompt,
                "raw_output": raw_output,
                "decision": decision,
                "rejection_reason": rejection_reason,
            }),
            ticker=ticker,
            candidate=candidate_payload,
            sources=sources,
            extractions=[
                ExtractionRef(
                    provider=f"equity_{stage}",
                    raw_hash=raw_hash,
                    content_hash=stable_hash(output_json or raw_output),
                )
            ],
            llm_model=llm_model,
            prompt_hash=stable_hash(prompt),
            output_json=output_json,
            raw_output=raw_output,
            confidence=(output_json or {}).get("confidence") if output_json else None,
            decision=decision,  # type: ignore[arg-type]
            rejection_reason=rejection_reason,
        )
        self._artifact_store.append(artifact)

    def _record_recommendation_artifact(
        self,
        rec: Recommendation,
        *,
        stage: str,
        llm_model: str,
        prompt: str,
        raw_output: str,
        output_json: dict[str, Any] | None,
        decision: str,
        rejection_reason: str,
    ) -> None:
        candidate = getattr(self, "_candidate_by_ticker", {}).get(rec.instrument.ticker)
        if candidate is None:
            return
        self._record_artifact(
            candidate,
            price=rec.entry,
            news=[],
            filings=[],
            sector="",
            analyst_count=0,
            llm_model=llm_model,
            prompt=prompt,
            raw_output=raw_output,
            output_json=output_json,
            decision=decision,
            rejection_reason=rejection_reason,
            stage=stage,
        )

    def _challenge(
        self, rec: Recommendation
    ) -> tuple[Recommendation | None, list[str]]:
        """Run the challenger pass. Returns (adjusted_rec_or_None, objections)."""
        if not self._budget.allow(_CHALLENGER_COST):
            return rec, []

        ticker = rec.instrument.ticker
        headlines = self._news.headlines(ticker, limit=10) if self._news else []

        user_msg = build_challenger_prompt(
            ticker=ticker,
            entry=rec.entry,
            stop=rec.stop_loss or 0.0,
            target=rec.take_profit or 0.0,
            catalyst=rec.catalyst,
            thesis=rec.thesis,
            news=headlines,
        )
        try:
            resp = self._llm.complete(_CHALLENGER_SYSTEM, user_msg, _SONNET)
            self._budget.record(resp.cost_usd("sonnet"))
            data = parse_challenger_decision(resp.content)
        except LLMFailureBudgetExceeded:
            raise
        except Exception as exc:
            self._record_recommendation_artifact(
                rec,
                stage="challenger",
                llm_model=_SONNET,
                prompt=user_msg,
                raw_output=resp.content if "resp" in locals() else "",
                output_json=None,
                decision="error",
                rejection_reason=f"challenger_output_invalid:{exc}",
            )
            return rec, []

        objections = data.objections
        verdict = data.verdict

        if verdict == "reject":
            self._record_recommendation_artifact(
                rec,
                stage="challenger",
                llm_model=_SONNET,
                prompt=user_msg,
                raw_output=resp.content,
                output_json=data.model_dump(),
                decision="rejected",
                rejection_reason="challenger_reject",
            )
            return None, objections

        if verdict == "weaken":
            adj = float(data.confidence_adjustment)
            new_confidence = max(0.1, rec.confidence + adj)
            weakened = Recommendation(
                instrument=rec.instrument,
                sleeve=rec.sleeve,
                side=rec.side,
                entry=rec.entry,
                stop_loss=rec.stop_loss,
                take_profit=rec.take_profit,
                size_pct=rec.size_pct,
                confidence=round(new_confidence, 3),
                catalyst=rec.catalyst,
                thesis=rec.thesis,
                horizon=rec.horizon,
                memo=rec.memo,
            )
            return weakened, objections

        return rec, objections

    def _audit(
        self,
        rec: Recommendation,
        objections: list[str],
    ) -> Recommendation | None:
        """Run auditor pass. Applies consistency_penalty; returns None on fatal flaw."""
        if not self._budget.allow(_AUDITOR_COST):
            return rec

        user_msg = build_auditor_prompt(
            thesis=rec.thesis,
            objections=objections,
            catalyst=rec.catalyst,
        )
        try:
            resp = self._llm.complete(_AUDITOR_SYSTEM, user_msg, _SONNET)
            self._budget.record(resp.cost_usd("sonnet"))
            data = parse_auditor_decision(resp.content)
        except LLMFailureBudgetExceeded:
            raise
        except Exception as exc:
            self._record_recommendation_artifact(
                rec,
                stage="auditor",
                llm_model=_SONNET,
                prompt=user_msg,
                raw_output=resp.content if "resp" in locals() else "",
                output_json=None,
                decision="error",
                rejection_reason=f"auditor_output_invalid:{exc}",
            )
            return rec

        if data.verdict == "reject":
            self._record_recommendation_artifact(
                rec,
                stage="auditor",
                llm_model=_SONNET,
                prompt=user_msg,
                raw_output=resp.content,
                output_json=data.model_dump(),
                decision="rejected",
                rejection_reason="auditor_reject",
            )
            return None

        consistency_penalty = float(data.consistency_penalty)
        new_confidence = round(max(0.05, rec.confidence - consistency_penalty), 3)

        return Recommendation(
            instrument=rec.instrument,
            sleeve=rec.sleeve,
            side=rec.side,
            entry=rec.entry,
            stop_loss=rec.stop_loss,
            take_profit=rec.take_profit,
            size_pct=rec.size_pct,
            confidence=new_confidence,
            catalyst=rec.catalyst,
            thesis=rec.thesis,
            horizon=rec.horizon,
            memo=rec.memo,
        )


def _compute_build_action(
    analyst_confidence: float,
    consistency_penalty: float,
    regime: str = "neutral",
) -> tuple[str, float]:
    """Map composite score to build action and size_pct.

    composite = analyst_confidence - consistency_penalty, clamped [0, 1].
    Base thresholds:
      AGGRESSIVE_BUILD >= 0.75 -> 4%
      GRADUAL_BUILD    >= 0.60 -> 2%
      NIBBLE           >= 0.45 -> 1%
      WAIT             <  0.45 -> 0% (skip)

    Regime adjustments (Task 15):
      risk_off: thresholds tighten by +0.10
      risk_on:  thresholds loosen by -0.05
    """
    composite = max(0.0, min(1.0, analyst_confidence - consistency_penalty))
    offset = 0.0
    if regime == "risk_off":
        offset = 0.10
    elif regime == "risk_on":
        offset = -0.05
    t_aggressive = 0.75 + offset
    t_gradual = 0.60 + offset
    t_nibble = 0.45 + offset
    if composite >= t_aggressive:
        return "AGGRESSIVE_BUILD", 0.04
    if composite >= t_gradual:
        return "GRADUAL_BUILD", 0.02
    if composite >= t_nibble:
        return "NIBBLE", 0.01
    return "WAIT", 0.0


def _recommendation_json(rec: Recommendation) -> dict[str, Any]:
    return {
        "ticker": rec.instrument.ticker,
        "sleeve": rec.sleeve.value,
        "side": rec.side,
        "entry": rec.entry,
        "stop_loss": rec.stop_loss,
        "take_profit": rec.take_profit,
        "size_pct": rec.size_pct,
        "confidence": rec.confidence,
        "catalyst": rec.catalyst,
        "thesis": rec.thesis,
        "horizon": rec.horizon,
        "memo": rec.memo,
    }


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = [l for l in lines[1:] if not l.startswith("```")]
        return "\n".join(inner)
    return text
