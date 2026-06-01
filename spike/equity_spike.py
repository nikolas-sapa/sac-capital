"""
07-SPIKE — Equity synthesis proof.

Throwaway script. Run, eyeball, delete (or keep for 2-4 week forward tracking).

PURPOSE:
  Collect real data bundles for ~10 catalyst tickers so Claude Code can analyse
  them in-session (no API key needed — runs through your Claude Code subscription).

USAGE:
  uv run python spike/equity_spike.py          # collect + print all bundles
  uv run python spike/equity_spike.py --save   # also write spike/bundles_YYYY-MM-DD.json
  uv run python spike/equity_spike.py --tickers SMCI,CROX,XPEL

After running, Claude Code reads the output and performs Stage 1 + Stage 2 analysis.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import yfinance as yf


# ---------------------------------------------------------------------------
# Candidates — swap freely; keep ~10 small/mid-cap ($300M–$5B) US stocks
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


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def _price_summary(ticker: str) -> dict[str, Any]:
    t = yf.Ticker(ticker)
    hist = t.history(period="6mo", interval="1d")
    if hist.empty:
        return {"error": "no price data"}
    latest = float(hist["Close"].iloc[-1])
    mo1 = float(hist["Close"].iloc[-22]) if len(hist) >= 22 else latest
    mo3 = float(hist["Close"].iloc[-66]) if len(hist) >= 66 else latest
    high52 = float(hist["High"].max())
    low52 = float(hist["Low"].min())
    avg_vol_20d = float(hist["Volume"].tail(20).mean())
    return {
        "latest_close": round(latest, 2),
        "1mo_chg_pct": round((latest / mo1 - 1) * 100, 1),
        "3mo_chg_pct": round((latest / mo3 - 1) * 100, 1),
        "52w_high": round(high52, 2),
        "52w_low": round(low52, 2),
        "pct_from_52w_high": round((latest / high52 - 1) * 100, 1),
        "avg_vol_20d": int(avg_vol_20d),
    }


def _company_info(ticker: str) -> dict[str, Any]:
    t = yf.Ticker(ticker)
    try:
        info = t.info
        return {
            "name": info.get("longName", ticker),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "market_cap_m": round(info.get("marketCap", 0) / 1e6, 0),
            "employees": info.get("fullTimeEmployees"),
            "trailing_pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "ps_ratio": info.get("priceToSalesTrailing12Months"),
            "revenue_growth": info.get("revenueGrowth"),
            "gross_margins": info.get("grossMargins"),
            "analyst_count": info.get("numberOfAnalystOpinions"),
        }
    except Exception:
        return {"name": ticker}


def _earnings_summary(ticker: str) -> list[dict]:
    t = yf.Ticker(ticker)
    try:
        ed = t.earnings_dates
        if ed is None or ed.empty:
            return []
        results = []
        for idx, row in ed.head(6).iterrows():
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
    t = yf.Ticker(ticker)
    try:
        news = t.news or []
        return [
            item.get("content", {}).get("title", item.get("title", ""))
            for item in news[:n] if item
        ]
    except Exception:
        return []


def _sec_recent_filings(ticker: str, days: int = 90) -> list[str]:
    """Recent 8-K + 10-Q filing subjects from SEC EDGAR free API."""
    subjects: list[str] = []
    try:
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
        items_field = filings.get("items", [])

        cutoff = (date.today() - timedelta(days=days)).isoformat()
        for form, filed, items in zip(forms, dates, items_field):
            if form in ("8-K", "8-K/A", "10-Q", "10-K") and filed >= cutoff:
                desc = f"{form} ({filed})"
                if items:
                    desc += f" — Items: {items}"
                subjects.append(desc)
            if len(subjects) >= 6:
                break
    except Exception:
        pass
    return subjects


def build_bundle(ticker: str, hint: str) -> dict[str, Any]:
    """Collect all data for one ticker into a structured dict."""
    return {
        "ticker": ticker,
        "hint": hint,
        "info": _company_info(ticker),
        "prices": _price_summary(ticker),
        "earnings": _earnings_summary(ticker),
        "news": _news_headlines(ticker),
        "sec_filings": _sec_recent_filings(ticker),
    }


def format_bundle_text(b: dict) -> str:
    """Format a bundle as readable text for analyst review."""
    info = b.get("info", {})
    prices = b.get("prices", {})
    lines = [
        f"### {b['ticker']} — {info.get('name', b['ticker'])}",
        f"Hint: {b['hint']}",
        f"Sector: {info.get('sector', '?')} / {info.get('industry', '?')}",
        f"Market cap: ${info.get('market_cap_m', '?')}M  |  Analysts covering: {info.get('analyst_count', '?')}",
        f"Trailing PE: {info.get('trailing_pe', '?')}  |  Forward PE: {info.get('forward_pe', '?')}  |  P/S: {info.get('ps_ratio', '?')}",
        f"Revenue growth: {info.get('revenue_growth', '?')}  |  Gross margins: {info.get('gross_margins', '?')}",
        "",
        "**Price:**",
    ]
    if "error" in prices:
        lines.append("  No price data.")
    else:
        lines += [
            f"  Latest: ${prices['latest_close']}  |  1mo: {prices['1mo_chg_pct']:+.1f}%  |  3mo: {prices['3mo_chg_pct']:+.1f}%",
            f"  52w range: ${prices['52w_low']} – ${prices['52w_high']}  |  From high: {prices['pct_from_52w_high']:+.1f}%",
            f"  Avg vol 20d: {prices['avg_vol_20d']:,}",
        ]

    lines += ["", "**Earnings surprises (last 6 quarters):**"]
    for e in b.get("earnings", []):
        if e.get("actual") is not None:
            lines.append(f"  {e['date']}: est={e['est']}, actual={e['actual']}, surprise={e['surprise_pct']}%")

    lines += ["", "**Recent news:**"]
    for h in b.get("news", [])[:6]:
        if h:
            lines.append(f"  - {h}")

    lines += ["", "**Recent SEC filings (8-K / 10-Q / 10-K, last 90 days):**"]
    for f in b.get("sec_filings", []):
        lines.append(f"  - {f}")
    if not b.get("sec_filings"):
        lines.append("  None found.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", help="comma-separated ticker override")
    parser.add_argument("--save", action="store_true", help="write JSON to spike/bundles_YYYY-MM-DD.json")
    args = parser.parse_args()

    if args.tickers:
        candidates = [(t.strip().upper(), "") for t in args.tickers.split(",")]
    else:
        candidates = DEFAULT_CANDIDATES

    print(f"\n{'='*64}")
    print(f"07-SPIKE  Data Collection  {date.today()}")
    print(f"Tickers: {[t for t, _ in candidates]}")
    print(f"{'='*64}\n")

    bundles = []
    for ticker, hint in candidates:
        print(f"[{ticker}] fetching...", end=" ", flush=True)
        b = build_bundle(ticker, hint)
        bundles.append(b)
        time.sleep(0.4)
        price = b["prices"].get("latest_close", "?")
        cap = b["info"].get("market_cap_m", "?")
        print(f"${price}  cap=${cap}M  news={len(b['news'])}  filings={len(b['sec_filings'])}")

    print("\n" + "="*64)
    print("DATA BUNDLES — paste to Claude Code for analysis")
    print("="*64 + "\n")

    for b in bundles:
        print(format_bundle_text(b))
        print()

    if args.save:
        out = Path(__file__).parent / f"bundles_{date.today()}.json"
        out.write_text(json.dumps(bundles, indent=2, default=str))
        print(f"\nJSON saved to: {out}")

    print("\n" + "="*64)
    print("NEXT: Claude Code reads the bundles above and performs:")
    print("  Stage 1 (quick scan): rate each 1-10 for catalyst complexity")
    print("  Stage 2 (deep): thesis + entry/stop/target for top scorers")
    print("="*64)


if __name__ == "__main__":
    main()
