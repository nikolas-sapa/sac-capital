from __future__ import annotations

from dataclasses import dataclass

from equities.data.fundamentals import FundamentalsSnapshot


@dataclass(frozen=True)
class CoreReview:
    reviewer: str
    score: float
    verdict: str
    reasons: list[str]
    risks: list[str]


class QualityReviewer:
    name = "quality"

    def review(self, snap: FundamentalsSnapshot) -> CoreReview:
        score = 0.5
        reasons: list[str] = []
        risks: list[str] = []
        if snap.gross_margins is not None:
            reasons.append(f"gross_margins={snap.gross_margins:.0%}")
            score += min(0.25, max(0.0, snap.gross_margins - 0.35))
            if snap.gross_margins < 0.30:
                risks.append("gross margins below core quality threshold")
        if snap.operating_margins is not None:
            reasons.append(f"operating_margins={snap.operating_margins:.0%}")
            score += min(0.15, max(0.0, snap.operating_margins))
            if snap.operating_margins < 0:
                risks.append("negative operating margins")
        if snap.free_cash_flow_m is not None:
            reasons.append(f"fcf_m={snap.free_cash_flow_m:.0f}")
            if snap.free_cash_flow_m < 0:
                risks.append("negative free cash flow")
        return _review(self.name, score, reasons, risks)


class ValuationReviewer:
    name = "valuation"

    def review(self, snap: FundamentalsSnapshot) -> CoreReview:
        score = 0.5
        reasons: list[str] = []
        risks: list[str] = []
        pe = snap.forward_pe if snap.forward_pe is not None else snap.trailing_pe
        if pe is not None:
            reasons.append(f"pe={pe:.1f}")
            if pe > 70:
                risks.append("valuation multiple is extreme for DCA add")
            elif pe > 45:
                risks.append("valuation is elevated")
            else:
                score += max(0.0, (45 - pe) / 45) * 0.25
        if snap.peg_ratio is not None:
            reasons.append(f"peg={snap.peg_ratio:.2f}")
            if snap.peg_ratio > 3:
                risks.append("PEG ratio suggests growth is overpaid")
            elif snap.peg_ratio <= 2:
                score += 0.15
        return _review(self.name, score, reasons, risks, wait_only=True)


class BalanceSheetReviewer:
    name = "balance_sheet"

    def review(self, snap: FundamentalsSnapshot) -> CoreReview:
        score = 0.6
        reasons: list[str] = []
        risks: list[str] = []
        if snap.debt_to_equity is not None:
            reasons.append(f"debt_to_equity={snap.debt_to_equity:.1f}")
            if snap.debt_to_equity > 250:
                risks.append("debt-to-equity is above hard reject threshold")
            elif snap.debt_to_equity > 150:
                risks.append("leverage is elevated")
            else:
                score += 0.2
        if snap.free_cash_flow_m is not None:
            reasons.append(f"fcf_m={snap.free_cash_flow_m:.0f}")
            if snap.free_cash_flow_m < 0:
                risks.append("negative free cash flow weakens balance-sheet flexibility")
            else:
                score += 0.15
        return _review(self.name, score, reasons, risks)


class GrowthDurabilityReviewer:
    name = "growth_durability"

    def review(self, snap: FundamentalsSnapshot) -> CoreReview:
        score = 0.5
        reasons: list[str] = []
        risks: list[str] = []
        if snap.revenue_growth is not None:
            reasons.append(f"revenue_growth={snap.revenue_growth:+.0%}")
            if snap.revenue_growth < -0.05:
                risks.append("revenue is contracting faster than core tolerance")
            elif snap.revenue_growth > 0:
                score += min(0.25, snap.revenue_growth)
        eps = list(snap.eps_trend or [])
        if len(eps) >= 2:
            reasons.append(f"eps_trend={eps[-4:]}")
            if eps[-1] < eps[0]:
                risks.append("EPS trend is deteriorating")
            else:
                score += 0.15
        return _review(self.name, score, reasons, risks, wait_only=True)


def run_core_reviewers(snap: FundamentalsSnapshot) -> list[CoreReview]:
    reviewers = [
        QualityReviewer(),
        ValuationReviewer(),
        BalanceSheetReviewer(),
        GrowthDurabilityReviewer(),
    ]
    return [reviewer.review(snap) for reviewer in reviewers]


def format_core_reviews(reviews: list[CoreReview]) -> str:
    if not reviews:
        return ""
    lines: list[str] = []
    for review in reviews:
        reasons = "; ".join(review.reasons[:3]) or "no decisive positive evidence"
        risks = "; ".join(review.risks[:3]) or "none"
        lines.append(
            f"- {review.reviewer}: {review.verdict} score={review.score:.2f}; "
            f"reasons={reasons}; risks={risks}"
        )
    return "\n".join(lines)


def has_hard_reject(reviews: list[CoreReview]) -> bool:
    return any(review.verdict == "reject" for review in reviews)


def _review(
    reviewer: str,
    score: float,
    reasons: list[str],
    risks: list[str],
    wait_only: bool = False,
) -> CoreReview:
    score = max(0.0, min(1.0, score))
    if risks and not wait_only and score < 0.65:
        verdict = "reject"
    elif risks:
        verdict = "wait"
    else:
        verdict = "approve"
    return CoreReview(
        reviewer=reviewer,
        score=round(score, 4),
        verdict=verdict,
        reasons=reasons,
        risks=risks,
    )
