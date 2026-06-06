from __future__ import annotations

from dataclasses import asdict, dataclass

from equities.data.sentiment import SentimentSnapshot


@dataclass(frozen=True)
class AnalystPacket:
    ticker: str
    agent: str
    score: float
    verdict: str
    thesis_points: list[str]
    risks: list[str]
    citations: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class TechnicalAgent:
    def packet(self, ticker: str, current_price: float) -> AnalystPacket:
        if current_price <= 0:
            return AnalystPacket(ticker, "technical", -1.0, "reject", [], ["invalid price"], [])
        return AnalystPacket(
            ticker=ticker,
            agent="technical",
            score=0.1,
            verdict="neutral",
            thesis_points=["price is valid for risk/reward analysis"],
            risks=[],
            citations=[f"current_price={current_price:.2f}"],
        )


class NewsCatalystAgent:
    def packet(self, ticker: str, headlines: list[str]) -> AnalystPacket:
        if not headlines:
            return AnalystPacket(
                ticker,
                "news_catalyst",
                -0.2,
                "neutral",
                [],
                ["no recent headline evidence"],
                [],
            )
        catalyst_terms = ("approval", "beat", "contract", "guidance", "partnership", "launch")
        risk_terms = ("downgrade", "lawsuit", "probe", "recall", "delay", "miss")
        joined = " ".join(headlines).lower()
        score = 0.25 if any(term in joined for term in catalyst_terms) else 0.0
        risks = [headline for headline in headlines if any(term in headline.lower() for term in risk_terms)]
        adjusted_score = score - min(0.4, len(risks) * 0.15)
        verdict = "bearish" if risks and adjusted_score < 0 else "bullish" if adjusted_score > 0 else "neutral"
        return AnalystPacket(
            ticker=ticker,
            agent="news_catalyst",
            score=adjusted_score,
            verdict=verdict,
            thesis_points=headlines[:3] if score > 0 else [],
            risks=risks[:3],
            citations=headlines[:3],
        )


class SentimentAgent:
    def packet(self, snapshot: SentimentSnapshot) -> AnalystPacket:
        verdict = "neutral"
        if snapshot.net_score > 0.2:
            verdict = "bullish"
        elif snapshot.net_score < -0.2:
            verdict = "bearish"
        return AnalystPacket(
            ticker=snapshot.ticker,
            agent="sentiment",
            score=snapshot.net_score,
            verdict=verdict,
            thesis_points=[snapshot.summary] if snapshot.net_score > 0 else [],
            risks=[snapshot.summary] if snapshot.net_score < 0 else [],
            citations=[item.text for item in snapshot.evidence[:3]],
        )


class FundamentalAgent:
    def packet(self, ticker: str, sector: str = "", analyst_count: int = 0) -> AnalystPacket:
        points = []
        if sector:
            points.append(f"sector={sector}")
        if analyst_count < 5:
            points.append("under-followed relative to large-cap consensus setups")
        return AnalystPacket(
            ticker=ticker,
            agent="fundamental",
            score=0.15 if analyst_count < 5 else 0.0,
            verdict="bullish" if analyst_count < 5 else "neutral",
            thesis_points=points,
            risks=[],
            citations=points,
        )


class TradeSynthesizer:
    def rejection(self, packets: list[AnalystPacket]) -> dict[str, object] | None:
        if not packets:
            return None
        rejects = [packet for packet in packets if packet.verdict == "reject"]
        if rejects:
            return {
                "action": "reject",
                "reason": f"specialist_reject:{rejects[0].agent}",
                "specialist_packets": [packet.to_dict() for packet in packets],
            }
        bearish = [packet for packet in packets if packet.verdict == "bearish"]
        avg_score = sum(packet.score for packet in packets) / len(packets)
        if len(bearish) >= 2 and avg_score < -0.15:
            return {
                "action": "reject",
                "reason": "specialist_reject:multiple_bearish_packets",
                "specialist_packets": [packet.to_dict() for packet in packets],
            }
        return None


def format_packets(packets: list[AnalystPacket]) -> str:
    lines: list[str] = []
    for packet in packets:
        points = "; ".join(packet.thesis_points[:2]) or "none"
        risks = "; ".join(packet.risks[:2]) or "none"
        lines.append(
            f"- {packet.agent}: {packet.verdict} score={packet.score:+.2f}; "
            f"points={points}; risks={risks}"
        )
    return "\n".join(lines)
