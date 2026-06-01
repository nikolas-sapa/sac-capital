"""
07-SPIKE — Equity synthesis proof.

Throwaway script. Run, eyeball, delete (or keep for 2-4 week forward tracking).

PURPOSE:
  Prove Claude's synthesis is useful on hand-picked catalyst tickers BEFORE
  building the screening/risk machine. If Claude produces generic vibes instead
  of specific, document-grounded theses, kill the project here.

WHAT IT DOES:
  1. For each candidate ticker: pull price history, recent news, earnings
     surprise history, and recent SEC 8-K filing subjects.
  2. Stage 1 (Haiku): rate each ticker 1-10 for catalyst complexity.
  3. Stage 2 (Sonnet): write full Recommendation for the top-scoring tickers.
  4. Print to stdout + write spike/output_YYYY-MM-DD.md for eyeball review.

USAGE:
  uv run python spike/equity_spike.py
  uv run python spike/equity_spike.py --top 5        # stage-2 on top 5
  uv run python spike/equity_spike.py --tickers SMCI,CROX,XPEL

RESULT INTERPRETATION:
  GOOD: Theses cite specific filings, call transcripts, or earnings details.
        Entry/stop levels are grounded in the price action shown.
        Claude says PASS on setups where the re-rating already happened.
  BAD:  Generic language ("strong fundamentals", "growth potential").
        All 10 tickers get BUY ratings with identical confidence.
        No specific catalyst cited.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import yfinance as yf
import anthropic

# ---------------------------------------------------------------------------
# Candidates — swap these freely; keep ~10 small/mid-cap ($300M–$5B) US stocks
# with an active story. The spike validates the METHOD, not the picks.
# ---------------------------------------------------------------------------
DEFAULT_CANDIDATES: list[tuple[str, str]] = [
    ("SMCI",  "AI server infrastructure, extreme earnings volatility, SEC filing issues"),
    ("XPEL",  "auto aftermarket protection film, thin analyst coverage, expansion story"),
    ("PGNY",  "fertility benefits SaaS, employer-headwinds debate, under-covered"),
    ("FIGS",  "medical apparel DTC, recovery thesis vs. competition narrative"),
    ("PRCT",  "medtech urology robotics, early commercial ramp, complex clinical story"),
    ("BOOT",  "specialty retail western wear, same-store sales + margin story"),
    ("KLIC",  "semiconductor equipment, earnings sensitivity, capacity cycle position"),
    ("CURV",  "plus-size fashion retail, turnaround or terminal decline?"),
    ("ARWR",  "RNA interference biotech, pipeline catalyst timing, thin sell-side"),
    ("IPAR",  "fragrance/beauty IP licensor, steady compounder, under-followed"),
]

STAGE1_SYSTEM = """You are a junior equity analyst at a small activist fund.
Your job is to rate stock opportunities 1-10 for "catalyst complexity" — meaning:
how much genuine analytical work is required to understand whether the current price
reflects the full story? High scores go to situations where:
- The thesis is buried in filings, call transcripts, or segment disclosures
- Analyst consensus lags because the story is multi-step or technically complex
- There is a SPECIFIC upcoming catalyst (earnings, ruling, product launch, re-rating trigger)
Low scores go to:
- Simple stories already well-covered by sell-side
- "Already moved" setups (re-rating complete, upside priced in)
- No clear catalyst in the next 1–6 weeks

Respond with ONLY valid JSON:
{"score": <int 1-10>, "reason": "<1 sentence>", "pass": <true if you would skip entirely>}
"""

STAGE2_SYSTEM = """You are a senior equity analyst at a small activist fund.
Your edge is synthesis: you read complex, multi-source stories (filings, call transcripts,
earnings surprises) faster than the street and get positioned before re-ratings complete.

RULES:
1. REJECT and output {{"action": "PASS", "reason": "<why already priced / no edge>"}} if:
   - The re-rating is clearly already complete (stock already moved on the news)
   - The thesis is generic ("strong growth trajectory", "market leader")
   - You cannot cite a SPECIFIC document, number, or event from the context
2. For SWING sleeve (days-to-weeks):
   - Entry near current price or on a defined level
   - Stop-loss below a specific support / below the catalyst level
   - Take-profit at a specific level justified by the thesis
   - Confidence = your honest probability of being correct (0.0–1.0); be conservative
3. Horizon: 1–4 weeks (synthesis edge, not reaction-speed play)

Respond with ONLY valid JSON matching one of these shapes:
{{
  "action": "PASS",
  "reason": "<specific reason>"
}}
OR
{{
  "action": "RECOMMEND",
  "sleeve": "swing",
  "side": "buy",
  "entry": <float>,
  "stop_loss": <float>,
  "take_profit": <float>,
  "horizon": "<e.g. 2-3 weeks>",
  "confidence": <float 0.0-1.0>,
  "catalyst": "<specific event>",
  "thesis": "<2-3 sentences, cite specific numbers/filings>",
  "incomplete_rerating": "<why the re-rating is NOT yet complete>"
}}
"""


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def _price_summary(ticker: str) -> dict[str, Any]:
    """Pull 6-month price history; return summary dict."""
    t = yf.Ticker(ticker)
    hist = t.history(period="6mo", interval="1d")
    if hist.empty:
        return {"error": "no price data"}
    latest = float(hist["Close"].iloc[-1])
    mo1 = float(hist["Close"].iloc[-22]) if len(hist) >= 22 else latest
    mo3 = float(hist["Close"].iloc[-66]) if len(hist) >= 66 else latest
    high52 = float(hist["High"].max())
    low52 = float(hist["Low"].min())
    return {
        "latest_close": round(latest, 2),
        "1mo_chg_pct": round((latest / mo1 - 1) * 100, 1),
        "3mo_chg_pct": round((latest / mo3 - 1) * 100, 1),
        "52w_high": round(high52, 2),
        "52w_low": round(low52, 2),
        "pct_from_52w_high": round((latest / high52 - 1) * 100, 1),
    }


def _earnings_summary(ticker: str) -> list[dict]:
    """Return last 4 quarterly earnings surprises if available."""
    t = yf.Ticker(ticker)
    try:
        ed = t.earnings_dates
        if ed is None or ed.empty:
            return []
        results = []
        for idx, row in ed.head(4).iterrows():
            est = row.get("EPS Estimate")
            act = row.get("Reported EPS")
            surprise = row.get("Surprise(%)")
            results.append({
                "date": str(idx.date()) if hasattr(idx, "date") else str(idx),
                "est": round(float(est), 3) if est is not None and est == est else None,
                "actual": round(float(act), 3) if act is not None and act == act else None,
                "surprise_pct": round(float(surprise), 1) if surprise is not None and surprise == surprise else None,
            })
        return results
    except Exception:
        return []


def _news_headlines(ticker: str, n: int = 8) -> list[str]:
    """Return recent news headlines via yfinance."""
    t = yf.Ticker(ticker)
    try:
        news = t.news or []
        return [item.get("content", {}).get("title", item.get("title", "")) for item in news[:n] if item]
    except Exception:
        return []


def _sec_recent_8k_subjects(ticker: str, days: int = 90) -> list[str]:
    """
    Fetch subjects of recent 8-K filings from SEC EDGAR free API.
    Returns list of filing descriptions (form type + date + items).
    """
    subjects: list[str] = []
    try:
        # Step 1: resolve ticker → CIK via EDGAR company_tickers.json
        r = httpx.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": "equity-spike nikolas.sapalidis@gmail.com"},
            timeout=10,
        )
        if r.status_code != 200:
            return subjects
        cik_map = r.json()
        cik = None
        for _, v in cik_map.items():
            if v.get("ticker", "").upper() == ticker.upper():
                cik = str(v["cik_str"]).zfill(10)
                break
        if not cik:
            return subjects

        # Step 2: get submissions (recent filings)
        r2 = httpx.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers={"User-Agent": "equity-spike nikolas.sapalidis@gmail.com"},
            timeout=10,
        )
        if r2.status_code != 200:
            return subjects
        data = r2.json()
        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        dates = filings.get("filingDate", [])
        descriptions = filings.get("primaryDocument", [])
        items_field = filings.get("items", [])

        cutoff = (date.today() - timedelta(days=days)).isoformat()
        for form, filed, doc, items in zip(forms, dates, descriptions, items_field):
            if form in ("8-K", "8-K/A") and filed >= cutoff:
                desc = f"{form} ({filed})"
                if items:
                    desc += f" — Items: {items}"
                subjects.append(desc)
            if len(subjects) >= 5:
                break
    except Exception:
        pass
    return subjects


def build_context_bundle(ticker: str, hint: str) -> str:
    """Assemble a ~600-token context bundle for a ticker."""
    prices = _price_summary(ticker)
    earnings = _earnings_summary(ticker)
    news = _news_headlines(ticker)
    filings = _sec_recent_8k_subjects(ticker)

    lines = [
        f"TICKER: {ticker}",
        f"CONTEXT HINT: {hint}",
        "",
        "## Price",
    ]
    if "error" in prices:
        lines.append("  No price data available.")
    else:
        lines += [
            f"  Latest close:  ${prices['latest_close']}",
            f"  1-month chg:   {prices['1mo_chg_pct']:+.1f}%",
            f"  3-month chg:   {prices['3mo_chg_pct']:+.1f}%",
            f"  52w high/low:  ${prices['52w_high']} / ${prices['52w_low']}",
            f"  From 52w high: {prices['pct_from_52w_high']:+.1f}%",
        ]

    lines.append("")
    lines.append("## Recent Earnings Surprises (last 4 quarters)")
    if earnings:
        for e in earnings:
            s = f"  {e['date']}: EPS est={e['est']}, actual={e['actual']}, surprise={e['surprise_pct']}%"
            lines.append(s)
    else:
        lines.append("  No earnings data available.")

    lines.append("")
    lines.append("## Recent News Headlines")
    if news:
        for h in news[:6]:
            if h:
                lines.append(f"  - {h}")
    else:
        lines.append("  No recent news.")

    lines.append("")
    lines.append("## Recent SEC 8-K Filings (last 90 days)")
    if filings:
        for f in filings:
            lines.append(f"  - {f}")
    else:
        lines.append("  No recent 8-K filings found.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Claude calls
# ---------------------------------------------------------------------------

def stage1_rate(client: anthropic.Anthropic, ticker: str, bundle: str) -> dict:
    """Haiku: rate the ticker 1-10 for catalyst complexity."""
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system=STAGE1_SYSTEM,
        messages=[{"role": "user", "content": bundle}],
    )
    raw = msg.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"score": 0, "reason": f"parse error: {raw[:100]}", "pass": True}


def stage2_analyse(client: anthropic.Anthropic, ticker: str, bundle: str) -> dict:
    """Sonnet: write full Recommendation for a top-scoring ticker."""
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        system=STAGE2_SYSTEM,
        messages=[{"role": "user", "content": bundle}],
    )
    raw = msg.content[0].text.strip()
    # strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return {"action": "PARSE_ERROR", "raw": raw[:300]}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def render_recommendation(ticker: str, score: int, stage1: dict, stage2: dict) -> str:
    lines = [f"\n### {ticker} (Haiku score: {score}/10)"]
    lines.append(f"**Catalyst interest:** {stage1.get('reason', '')}")
    action = stage2.get("action", "?")
    if action == "PASS":
        lines.append(f"**Sonnet: PASS** — {stage2.get('reason', '')}")
    elif action == "RECOMMEND":
        lines += [
            f"**Sonnet: RECOMMEND {stage2.get('sleeve', '').upper()} {stage2.get('side', '').upper()}**",
            f"- Entry: ${stage2.get('entry')}  |  Stop: ${stage2.get('stop_loss')}  |  Target: ${stage2.get('take_profit')}",
            f"- Horizon: {stage2.get('horizon')}  |  Confidence: {stage2.get('confidence')}",
            f"- Catalyst: {stage2.get('catalyst')}",
            f"- Thesis: {stage2.get('thesis')}",
            f"- Why re-rating incomplete: {stage2.get('incomplete_rerating')}",
        ]
    else:
        lines.append(f"**Sonnet: {action}** — {stage2.get('raw', '')[:200]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", help="comma-separated override list")
    parser.add_argument("--top", type=int, default=4, help="how many to send to Stage 2 (default 4)")
    args = parser.parse_args()

    if args.tickers:
        candidates = [(t.strip().upper(), "") for t in args.tickers.split(",")]
    else:
        candidates = DEFAULT_CANDIDATES

    # Load API key from core.config
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from core.config import load_config
    cfg = load_config()
    if not cfg.anthropic_api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)

    print(f"\n{'='*60}")
    print(f"07-SPIKE  Equity Synthesis Proof  {date.today()}")
    print(f"{'='*60}")
    print(f"Candidates: {[t for t, _ in candidates]}")
    print(f"Stage 1 model: claude-haiku-4-5-20251001")
    print(f"Stage 2 model: claude-sonnet-4-6  (top {args.top})")
    print()

    # --- Stage 1: collect + rate all candidates ---
    bundles: dict[str, str] = {}
    ratings: dict[str, dict] = {}

    for ticker, hint in candidates:
        print(f"[{ticker}] fetching data...", end=" ", flush=True)
        bundle = build_context_bundle(ticker, hint)
        bundles[ticker] = bundle
        time.sleep(0.5)  # be polite to yfinance + SEC

        print("rating...", end=" ", flush=True)
        rating = stage1_rate(client, ticker, bundle)
        ratings[ticker] = rating
        score = rating.get("score", 0)
        skip = rating.get("pass", False)
        print(f"score={score}/10  {'[SKIP]' if skip else ''}  {rating.get('reason', '')[:60]}")

    # --- Sort by score, filter out explicit passes ---
    ranked = sorted(
        [(t, ratings[t]) for t in ratings if not ratings[t].get("pass", False)],
        key=lambda x: x[1].get("score", 0),
        reverse=True,
    )

    print(f"\n--- Stage 1 ranking ---")
    for rank, (t, r) in enumerate(ranked, 1):
        print(f"  {rank}. {t:6s}  {r.get('score', 0)}/10  {r.get('reason', '')[:70]}")

    top_tickers = [t for t, _ in ranked[: args.top]]
    print(f"\n--- Stage 2 analysis (Sonnet) on: {top_tickers} ---\n")

    recommendations: list[tuple[str, dict, dict]] = []
    for ticker in top_tickers:
        print(f"[{ticker}] analysing...", end=" ", flush=True)
        rec = stage2_analyse(client, ticker, bundles[ticker])
        action = rec.get("action", "?")
        print(f"→ {action}")
        recommendations.append((ticker, ratings[ticker], rec))

    # --- Print report ---
    report_lines = [
        f"# 07-SPIKE Equity Synthesis Report — {date.today()}",
        "",
        "**Purpose:** eyeball whether Claude produces specific, document-grounded theses",
        "or generic vibes. Specific + grounded = proceed to 07b. Generic = kill project.",
        "",
        "## Stage 1 — All candidates (Haiku)",
        "",
        "| Ticker | Score | Reason | Skip |",
        "|--------|-------|--------|------|",
    ]
    for t, r in sorted(ratings.items(), key=lambda x: x[1].get("score", 0), reverse=True):
        report_lines.append(
            f"| {t} | {r.get('score', 0)}/10 | {r.get('reason', '')[:60]} | {'✓' if r.get('pass') else ''} |"
        )

    report_lines += ["", "## Stage 2 — Detailed analysis (Sonnet)", ""]
    for ticker, stage1, stage2 in recommendations:
        report_lines.append(render_recommendation(ticker, stage1.get("score", 0), stage1, stage2))
        report_lines.append("")

    report_lines += [
        "---",
        "## Eyeball Checklist",
        "- [ ] Do theses cite specific filings / earnings numbers / call details?",
        "- [ ] Are PASS calls on setups where price already moved?",
        "- [ ] Are entry/stop levels grounded in the price data shown?",
        "- [ ] Is confidence < 0.7 on uncertain setups (honest calibration)?",
        "- [ ] Any generic language ('strong fundamentals', 'market leader') — red flag",
        "",
        "**Result:** PROCEED / KILL (fill in after eyeballing)",
        "",
        f"_Generated {datetime.now().isoformat()}_",
    ]

    report = "\n".join(report_lines)
    print("\n" + "="*60)
    print(report)

    out_path = Path(__file__).parent / f"output_{date.today()}.md"
    out_path.write_text(report)
    print(f"\n\nReport saved to: {out_path}")


if __name__ == "__main__":
    main()
