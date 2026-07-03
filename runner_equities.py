"""Equities runner — screen → analyse → risk-gate → paper-open → nightly mark.

Usage:
    uv run python runner_equities.py                    # single pass
    uv run python runner_equities.py --no-analyse       # screen only (no LLM)
    uv run python runner_equities.py --mark-only        # mark-to-market + exit check
    uv run python runner_equities.py --reconcile-only   # broker reconciliation only

Uses LLM_PROVIDER=codex/openai/claude; this Mac is configured for Codex CLI.
All trades are paper-only; LIVE mode does not exist yet.
"""
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import socket
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from core.alerts.telegram import TelegramAlerts
from core.assets.instrument import CapTier, Instrument
from core.config import load_config
from core.claude_client import ClaudeCodeClient
from equities.analysis.analyst import EquityAnalyst, LLMFailureBudgetExceeded, LLMResponse
from equities.analysis.budget import DailyBudget
from equities.analysis.checkpoint import AnalysisCheckpointStore
from equities.analysis.core_analyst import CoreDCAAnalyst
from equities.data.news import YFinanceNewsProvider
from equities.data.news_composite import CompositeNewsProvider
from equities.data.news_crawl4ai import Crawl4AINewsProvider
from equities.data.news_tiingo import TiingoNewsProvider
from equities.data.registry import ProviderRegistry
from equities.data.macro_regime import MacroRegimeGate
from equities.data.vix import VIXRegimeGate
from equities.data.calendar import YFinanceCalendar
from equities.data.filings import SECEdgarFilings
from equities.data.fundamentals import YFinanceFundamentals
from equities.data.prices import YFinancePriceFeed
from equities.data.yfinance_utils import IsolatedCall
from equities.execution.alpaca import AlpacaPaperExecutor, client_order_id_for
from equities.killgate.tracker import ForwardPaperTracker
from equities.ledger_equity import EquityLedger
from equities.paper import EquityPaperTracker, PaperFill
from equities.risk.kernel import RiskKernel
from equities.killgate.thesis_health import ThesisHealthChecker
from equities.research.artifacts import risk_decision_artifact
from equities.research.run_manifest import build_run_manifest, settings_snapshot
from equities.research.store import ResearchArtifactStore
from equities.screen.inflection_screen import InflectionScanner
from equities.screen.relative_strength import RelativeStrengthScanner
from equities.screen.thematic_monitor import ThematicMonitor
from equities.screen.event_screen import (
    CalendarAdapter,
    EventScreen,
    FilingsAdapter,
)
from equities.screen.quality_screen import QualityScreen
from equities.screen.politician_screen import PoliticianScreen
from equities.data.house_clerk_disclosures import HouseClerkDisclosureProvider
from equities.data.senate_efd_disclosures import SenateEFDDisclosureProvider
from equities.data.executive_disclosures import ExecutiveDisclosureProvider
from equities.data.composite_disclosures import CompositeDisclosureProvider
from equities.data.fund_13f import Fund13FProvider

# ---------------------------------------------------------------------------
# Default universe (extend via --universe flag or editing this list)
# ---------------------------------------------------------------------------

DEFAULT_SWING_UNIVERSE: list[Instrument] = [
    # Semiconductor equipment & packaging
    Instrument("KLIC",  "Kulicke and Soffa",          "NASDAQ", CapTier.MID),
    Instrument("ONTO",  "Onto Innovation",            "NYSE",   CapTier.MID),
    Instrument("LRCX",  "Lam Research",               "NASDAQ", CapTier.LARGE),
    Instrument("KLAC",  "KLA Corporation",            "NASDAQ", CapTier.LARGE),
    Instrument("ENTG",  "Entegris",                   "NASDAQ", CapTier.MID),
    Instrument("AMKR",  "Amkor Technology",           "NASDAQ", CapTier.MID),
    # AI chips & semiconductor infrastructure
    Instrument("AMD",   "Advanced Micro Devices",     "NASDAQ", CapTier.LARGE),
    Instrument("MU",    "Micron Technology",          "NASDAQ", CapTier.LARGE),
    Instrument("MRVL",  "Marvell Technology",         "NASDAQ", CapTier.MID),
    Instrument("ALAB",  "Astera Labs",                "NASDAQ", CapTier.SMALL),
    Instrument("NBIS",  "Nebius Group",               "NASDAQ", CapTier.SMALL),
    Instrument("QCOM",  "Qualcomm",                   "NASDAQ", CapTier.LARGE),
    Instrument("SMCI",  "Super Micro Computer",       "NASDAQ", CapTier.MID),
    # Optical / connectivity (NVIDIA supply chain)
    Instrument("COHR",  "Coherent Corp",              "NYSE",   CapTier.MID),
    Instrument("LITE",  "Lumentum Holdings",          "NASDAQ", CapTier.MID),
    Instrument("AAOI",  "Applied Optoelectronics",    "NASDAQ", CapTier.SMALL),
    Instrument("FN",    "Fabrinet",                   "NYSE",   CapTier.MID),
    Instrument("APH",   "Amphenol",                   "NYSE",   CapTier.LARGE),
    Instrument("AXTI",  "AXT Inc",                    "NASDAQ", CapTier.SMALL),
    Instrument("VIAV",  "VIAVI Solutions",            "NASDAQ", CapTier.MID),
    # AI server ODM / construction
    Instrument("CLS",   "Celestica",                  "NYSE",   CapTier.MID),
    Instrument("FIX",   "Comfort Systems USA",        "NYSE",   CapTier.MID),
    # Power grid & nuclear
    Instrument("CEG",   "Constellation Energy",       "NASDAQ", CapTier.LARGE),
    Instrument("GEV",   "GE Vernova",                 "NYSE",   CapTier.LARGE),
    Instrument("ETN",   "Eaton Corporation",          "NYSE",   CapTier.LARGE),
    Instrument("PWR",   "Quanta Services",            "NYSE",   CapTier.LARGE),
    Instrument("VRT",   "Vertiv Holdings",            "NYSE",   CapTier.MID),
    # High-growth / catalyst plays
    Instrument("PLTR",  "Palantir",                   "NASDAQ", CapTier.MID),
    Instrument("HOOD",  "Robinhood",                  "NASDAQ", CapTier.MID),
    Instrument("COIN",  "Coinbase",                   "NASDAQ", CapTier.MID),
    Instrument("RKLB",  "Rocket Lab",                 "NASDAQ", CapTier.SMALL),
    Instrument("SOFI",  "SoFi Technologies",          "NASDAQ", CapTier.MID),
    Instrument("APP",   "AppLovin",                   "NASDAQ", CapTier.MID),
    Instrument("AXON",  "Axon Enterprise",            "NASDAQ", CapTier.MID),
    Instrument("CRWD",  "CrowdStrike",                "NASDAQ", CapTier.LARGE),
    Instrument("NET",   "Cloudflare",                 "NYSE",   CapTier.MID),
    Instrument("DDOG",  "Datadog",                    "NASDAQ", CapTier.MID),
    Instrument("SNOW",  "Snowflake",                  "NYSE",   CapTier.MID),
    Instrument("XYZ",   "Block",                      "NYSE",   CapTier.MID),
    Instrument("AFRM",  "Affirm",                     "NASDAQ", CapTier.MID),
    Instrument("NU",    "Nu Holdings",                "NYSE",   CapTier.MID),
    Instrument("TSLA",  "Tesla",                      "NASDAQ", CapTier.LARGE),
    Instrument("ARM",   "Arm Holdings",               "NASDAQ", CapTier.LARGE),
    Instrument("CVNA",  "Carvana",                    "NYSE",   CapTier.MID),
    Instrument("SOUN",  "SoundHound AI",              "NASDAQ", CapTier.SMALL),
    Instrument("XPEL",  "XPEL",                       "NASDAQ", CapTier.SMALL),
    # Cybersecurity
    Instrument("ZS",    "Zscaler",                    "NASDAQ", CapTier.MID),
    Instrument("S",     "SentinelOne",                "NYSE",   CapTier.MID),
    Instrument("PANW",  "Palo Alto Networks",         "NASDAQ", CapTier.LARGE),
    Instrument("FTNT",  "Fortinet",                   "NASDAQ", CapTier.LARGE),
    # Cloud / AI SaaS
    Instrument("NOW",   "ServiceNow",                 "NYSE",   CapTier.LARGE),
    Instrument("CRM",   "Salesforce",                 "NYSE",   CapTier.LARGE),
    Instrument("MNDY",  "Monday.com",                 "NASDAQ", CapTier.MID),
    Instrument("HUBS",  "HubSpot",                    "NYSE",   CapTier.MID),
    Instrument("MDB",   "MongoDB",                    "NASDAQ", CapTier.MID),
    Instrument("TTD",   "The Trade Desk",             "NASDAQ", CapTier.MID),
    Instrument("VEEV",  "Veeva Systems",              "NYSE",   CapTier.LARGE),
    # E-commerce / consumer tech
    Instrument("SHOP",  "Shopify",                    "NYSE",   CapTier.LARGE),
    Instrument("MELI",  "MercadoLibre",               "NASDAQ", CapTier.LARGE),
    Instrument("TOST",  "Toast",                      "NYSE",   CapTier.MID),
    Instrument("GLBE",  "Global-E Online",            "NASDAQ", CapTier.SMALL),
    Instrument("UBER",  "Uber",                       "NYSE",   CapTier.LARGE),
    Instrument("PYPL",  "PayPal",                     "NASDAQ", CapTier.LARGE),
    Instrument("FOUR",  "Shift4 Payments",            "NYSE",   CapTier.MID),
    # Defense / space
    Instrument("KTOS",  "Kratos Defense",             "NASDAQ", CapTier.MID),
    Instrument("AVAV",  "AeroVironment",              "NASDAQ", CapTier.MID),
    Instrument("ASTS",  "AST SpaceMobile",            "NASDAQ", CapTier.SMALL),
    Instrument("LUNR",  "Intuitive Machines",         "NASDAQ", CapTier.SMALL),
    # Healthcare AI / consumer growth
    Instrument("TEM",   "Tempus AI",                  "NASDAQ", CapTier.MID),
    Instrument("GEHC",  "GE HealthCare",              "NASDAQ", CapTier.LARGE),
    Instrument("DOCS",  "Doximity",                   "NYSE",   CapTier.MID),
    Instrument("HIMS",  "Hims & Hers",                "NYSE",   CapTier.SMALL),
    Instrument("DUOL",  "Duolingo",                   "NASDAQ", CapTier.MID),
    Instrument("ONON",  "On Holding",                 "NYSE",   CapTier.MID),
    Instrument("DKNG",  "DraftKings",                 "NASDAQ", CapTier.MID),
    # Market laggards / re-rating plays
    Instrument("ADBE",  "Adobe",                      "NASDAQ", CapTier.LARGE),
    Instrument("VST",   "Vistra Energy",              "NYSE",   CapTier.LARGE),
    Instrument("TDC",   "Teradata",                   "NYSE",   CapTier.MID),
    Instrument("PGY",   "Pagaya Technologies",        "NASDAQ", CapTier.SMALL),
    Instrument("JBL",   "Jabil",                      "NYSE",   CapTier.LARGE),
    # Non-AI laggards / policy-sensitive re-rating plays
    Instrument("PFE",   "Pfizer",                     "NYSE",   CapTier.LARGE),
    Instrument("BMY",   "Bristol Myers Squibb",       "NYSE",   CapTier.LARGE),
    Instrument("CVS",   "CVS Health",                 "NYSE",   CapTier.LARGE),
    Instrument("HUM",   "Humana",                     "NYSE",   CapTier.LARGE),
    Instrument("TMO",   "Thermo Fisher Scientific",   "NYSE",   CapTier.LARGE),
    Instrument("DHR",   "Danaher",                    "NYSE",   CapTier.LARGE),
    Instrument("BAC",   "Bank of America",            "NYSE",   CapTier.LARGE),
    Instrument("C",     "Citigroup",                  "NYSE",   CapTier.LARGE),
    Instrument("SCHW",  "Charles Schwab",             "NYSE",   CapTier.LARGE),
    Instrument("BX",    "Blackstone",                 "NYSE",   CapTier.LARGE),
    Instrument("KKR",   "KKR",                        "NYSE",   CapTier.LARGE),
    Instrument("DIS",   "Disney",                     "NYSE",   CapTier.LARGE),
    Instrument("NKE",   "Nike",                       "NYSE",   CapTier.LARGE),
    Instrument("SBUX",  "Starbucks",                  "NASDAQ", CapTier.LARGE),
    Instrument("TGT",   "Target",                     "NYSE",   CapTier.LARGE),
    Instrument("LULU",  "Lululemon",                  "NASDAQ", CapTier.LARGE),
    Instrument("EL",    "Estee Lauder",               "NYSE",   CapTier.LARGE),
    Instrument("HD",    "Home Depot",                 "NYSE",   CapTier.LARGE),
    Instrument("LOW",   "Lowe's",                     "NYSE",   CapTier.LARGE),
    Instrument("LEN",   "Lennar",                     "NYSE",   CapTier.LARGE),
    Instrument("DHI",   "D.R. Horton",                "NYSE",   CapTier.LARGE),
    Instrument("CBRE",  "CBRE Group",                 "NYSE",   CapTier.LARGE),
    Instrument("PLD",   "Prologis",                   "NYSE",   CapTier.LARGE),
    Instrument("OXY",   "Occidental Petroleum",       "NYSE",   CapTier.LARGE),
    Instrument("SLB",   "SLB",                        "NYSE",   CapTier.LARGE),
    Instrument("LNG",   "Cheniere Energy",            "NYSE",   CapTier.LARGE),
    Instrument("FSLR",  "First Solar",                "NASDAQ", CapTier.LARGE),
    Instrument("NEE",   "NextEra Energy",             "NYSE",   CapTier.LARGE),
    Instrument("FCX",   "Freeport-McMoRan",           "NYSE",   CapTier.LARGE),
    Instrument("NUE",   "Nucor",                      "NYSE",   CapTier.LARGE),
    Instrument("CAT",   "Caterpillar",                "NYSE",   CapTier.LARGE),
    Instrument("DE",    "Deere",                      "NYSE",   CapTier.LARGE),
    Instrument("UPS",   "UPS",                        "NYSE",   CapTier.LARGE),
    Instrument("FDX",   "FedEx",                      "NYSE",   CapTier.LARGE),
    Instrument("LMT",   "Lockheed Martin",            "NYSE",   CapTier.LARGE),
    Instrument("RTX",   "RTX",                        "NYSE",   CapTier.LARGE),
    Instrument("NOC",   "Northrop Grumman",           "NYSE",   CapTier.LARGE),
    Instrument("GD",    "General Dynamics",           "NYSE",   CapTier.LARGE),
    # Edge AI / robotics
    Instrument("AMBA",  "Ambarella",                  "NASDAQ", CapTier.SMALL),
    Instrument("PRCT",  "PROCEPT BioRobotics",        "NASDAQ", CapTier.MID),
    # Inference / new IPOs
    Instrument("CBRS",  "Cerebras Systems",           "NASDAQ", CapTier.MID),
    Instrument("AI",    "C3.ai",                      "NYSE",   CapTier.SMALL),
]

DEFAULT_CORE_UNIVERSE: list[Instrument] = [
    # Quality large-caps — scored on fundamentals (margins, PE, growth)
    Instrument("MSFT",  "Microsoft",       "NASDAQ", CapTier.LARGE),
    Instrument("AAPL",  "Apple",           "NASDAQ", CapTier.LARGE),
    Instrument("GOOGL", "Alphabet",        "NASDAQ", CapTier.LARGE),
    Instrument("META",  "Meta Platforms",  "NASDAQ", CapTier.LARGE),
    Instrument("NVDA",  "NVIDIA",          "NASDAQ", CapTier.LARGE),
    Instrument("AMZN",  "Amazon",          "NASDAQ", CapTier.LARGE),
    Instrument("V",     "Visa",            "NYSE",   CapTier.LARGE),
    Instrument("MA",    "Mastercard",      "NYSE",   CapTier.LARGE),
    Instrument("JPM",   "JPMorgan Chase",  "NYSE",   CapTier.LARGE),
    Instrument("UNH",   "UnitedHealth",    "NYSE",   CapTier.LARGE),
    Instrument("LLY",   "Eli Lilly",       "NYSE",   CapTier.LARGE),
    Instrument("TSM",   "TSMC",            "NYSE",   CapTier.LARGE),
    Instrument("AVGO",  "Broadcom",        "NASDAQ", CapTier.LARGE),
    Instrument("ASML",  "ASML Holding",    "NASDAQ", CapTier.LARGE),
    Instrument("ORCL",  "Oracle",          "NYSE",   CapTier.LARGE),
    Instrument("COST",  "Costco",          "NASDAQ", CapTier.LARGE),
    Instrument("PFE",   "Pfizer",          "NYSE",   CapTier.LARGE),
    Instrument("BMY",   "Bristol Myers",   "NYSE",   CapTier.LARGE),
    Instrument("CVS",   "CVS Health",      "NYSE",   CapTier.LARGE),
    Instrument("TMO",   "Thermo Fisher",   "NYSE",   CapTier.LARGE),
    Instrument("DHR",   "Danaher",         "NYSE",   CapTier.LARGE),
    Instrument("BAC",   "Bank of America", "NYSE",   CapTier.LARGE),
    Instrument("C",     "Citigroup",       "NYSE",   CapTier.LARGE),
    Instrument("SCHW",  "Charles Schwab",  "NYSE",   CapTier.LARGE),
    Instrument("BX",    "Blackstone",      "NYSE",   CapTier.LARGE),
    Instrument("KKR",   "KKR",             "NYSE",   CapTier.LARGE),
    Instrument("DIS",   "Disney",          "NYSE",   CapTier.LARGE),
    Instrument("NKE",   "Nike",            "NYSE",   CapTier.LARGE),
    Instrument("SBUX",  "Starbucks",       "NASDAQ", CapTier.LARGE),
    Instrument("HD",    "Home Depot",      "NYSE",   CapTier.LARGE),
    Instrument("LOW",   "Lowe's",          "NYSE",   CapTier.LARGE),
    Instrument("OXY",   "Occidental",      "NYSE",   CapTier.LARGE),
    Instrument("SLB",   "SLB",             "NYSE",   CapTier.LARGE),
    Instrument("LNG",   "Cheniere Energy", "NYSE",   CapTier.LARGE),
    Instrument("FSLR",  "First Solar",     "NASDAQ", CapTier.LARGE),
    Instrument("NEE",   "NextEra Energy",  "NYSE",   CapTier.LARGE),
    Instrument("FCX",   "Freeport-McMoRan", "NYSE",  CapTier.LARGE),
    Instrument("NUE",   "Nucor",           "NYSE",   CapTier.LARGE),
    Instrument("CAT",   "Caterpillar",     "NYSE",   CapTier.LARGE),
    Instrument("DE",    "Deere",           "NYSE",   CapTier.LARGE),
    Instrument("LMT",   "Lockheed Martin", "NYSE",   CapTier.LARGE),
    Instrument("RTX",   "RTX",             "NYSE",   CapTier.LARGE),
    Instrument("NOC",   "Northrop Grumman", "NYSE",  CapTier.LARGE),
    Instrument("GD",    "General Dynamics", "NYSE",  CapTier.LARGE),
]


# ---------------------------------------------------------------------------
# Price provider adapter (satisfies analyst.PriceProvider protocol)
# ---------------------------------------------------------------------------

class _PriceAdapter:
    _LATEST_SERIES_PERIODS = ("5d", "1mo", "3mo", "1y")

    def __init__(self, feed: YFinancePriceFeed, failure_callback=None, price_fallback=None) -> None:
        self._feed = feed
        self._cache = {}
        self._failure_callback = failure_callback
        self._price_fallback = price_fallback

    def latest_close(self, ticker: str) -> float | None:
        started = time.monotonic()
        try:
            series = self._latest_series(ticker)
            bar = series.latest
            duration = time.monotonic() - started
            if bar is not None:
                print(f"  [PROVIDER] source=yfinance_price ticker={ticker} ok duration_s={duration:.2f}")
                return bar.close

            if self._price_fallback is not None:
                fallback_price = self._price_fallback(ticker)
                if fallback_price is not None:
                    print(
                        f"  [PROVIDER] source=yfinance_price ticker={ticker} "
                        f"fallback=ledger duration_s={duration:.2f}"
                    )
                    return fallback_price

            print(f"  [PROVIDER] source=yfinance_price ticker={ticker} ok duration_s={duration:.2f}")
            if self._failure_callback is not None:
                self._failure_callback()
            return None
        except Exception as exc:
            duration = time.monotonic() - started
            print(
                f"  [PROVIDER] source=yfinance_price ticker={ticker} "
                f"error={exc} duration_s={duration:.2f}"
            )
            if self._failure_callback is not None:
                self._failure_callback()
            return None

    def latest_bar(self, ticker: str):
        started = time.monotonic()
        try:
            return self._latest_series(ticker).latest
        except Exception as exc:
            duration = time.monotonic() - started
            print(
                f"  [PROVIDER] source=yfinance_price_latest_bar ticker={ticker} "
                f"error={exc} duration_s={duration:.2f}"
            )
            if self._failure_callback is not None:
                self._failure_callback()
            raise

    def _latest_series(self, ticker: str):
        if ticker not in self._cache:
            series = None
            for period in self._LATEST_SERIES_PERIODS:
                candidate = self._feed.history(ticker, period=period)
                if candidate.bars:
                    series = candidate
                    if period != "5d":
                        print(
                            f"  [PROVIDER] source=yfinance_price ticker={ticker} "
                            f"fallback_period={period}"
                        )
                    break
                if series is None:
                    series = candidate
            self._cache[ticker] = series if series is not None else self._feed.history(ticker, period="5d")
        return self._cache[ticker]


@dataclass
class RunStats:
    started_monotonic: float
    max_runtime_seconds: int
    max_provider_failures: int
    max_llm_failures: int
    provider_failures: int = 0
    llm_failures: int = 0
    exit_reason: str = "complete"
    stages: list[tuple[str, str, float]] = field(default_factory=list)

    def elapsed(self) -> float:
        return time.monotonic() - self.started_monotonic

    def record_provider_failure(self) -> None:
        self.provider_failures += 1
        self.check_runtime()

    def record_llm_failure(self) -> None:
        self.llm_failures += 1
        if self.llm_failures > self.max_llm_failures:
            self.exit_reason = "max_llm_failures_exceeded"
            raise LLMFailureBudgetExceeded(
                f"runner exceeded LLM failure budget "
                f"{self.max_llm_failures} (seen={self.llm_failures})"
            )

    def check_runtime(self) -> None:
        if self.elapsed() > self.max_runtime_seconds:
            self.exit_reason = "max_runtime_exceeded"
            raise TimeoutError(
                f"runner exceeded max runtime {self.max_runtime_seconds}s "
                f"(elapsed={self.elapsed():.1f}s)"
            )
        if self.provider_failures > self.max_provider_failures:
            self.exit_reason = "max_provider_failures_exceeded"
            raise RuntimeError(
                f"runner exceeded provider failure budget "
                f"{self.max_provider_failures} (seen={self.provider_failures})"
            )
        if self.llm_failures > self.max_llm_failures:
            self.exit_reason = "max_llm_failures_exceeded"
            raise RuntimeError(
                f"runner exceeded LLM failure budget "
                f"{self.max_llm_failures} (seen={self.llm_failures})"
            )


@contextmanager
def _stage(stats: RunStats, name: str) -> Iterator[None]:
    stats.check_runtime()
    started = time.monotonic()
    print(f"\n[STAGE START] {name}")
    try:
        yield
    except Exception as exc:
        duration = time.monotonic() - started
        stats.stages.append((name, "fail", duration))
        stats.exit_reason = f"stage_failed:{name}"
        print(f"[STAGE FAIL] {name} duration_s={duration:.2f} error={exc}")
        raise
    else:
        duration = time.monotonic() - started
        stats.stages.append((name, "done", duration))
        print(f"[STAGE DONE] {name} duration_s={duration:.2f}")
        stats.check_runtime()


def _print_run_summary(
    stats: RunStats,
    budget: DailyBudget | None = None,
    provider_registry: ProviderRegistry | None = None,
) -> None:
    print("\n=== Run summary ===")
    print(f"exit_reason={stats.exit_reason}")
    print(f"elapsed_s={stats.elapsed():.2f}")
    print(f"provider_failures={stats.provider_failures}")
    print(f"llm_failures={stats.llm_failures}")
    for name, status, duration in stats.stages:
        print(f"stage={name} status={status} duration_s={duration:.2f}")
    if budget is not None:
        print(f"Budget used today: ${budget.spent_today():.4f}")
    if provider_registry is not None:
        failures = provider_registry.failures()
        if failures:
            print("Provider failures:")
            for health in failures:
                print(
                    f"provider={health.name} kind={health.kind} "
                    f"failures={health.failure_count} last_error={health.last_error}"
                )


class _FilingsSummaryAdapter:
    def __init__(self, client: SECEdgarFilings, failure_callback=None) -> None:
        self._client = client
        self._failure_callback = failure_callback

    def summary(self, ticker: str, days: int = 90) -> list[str]:
        started = time.monotonic()
        try:
            filings = self._client.recent(ticker, days=days)
        except Exception as exc:
            duration = time.monotonic() - started
            print(
                f"  [PROVIDER] source=sec_filings_summary ticker={ticker} "
                f"error={exc} duration_s={duration:.2f}"
            )
            if self._failure_callback is not None:
                self._failure_callback()
            return []
        return [
            f"{f.form_type} ({f.filed_date}) — items: {', '.join(f.items)}"
            for f in filings
        ]


class _LLMFailureCountingClient:
    def __init__(self, client: ClaudeCodeClient, stats: RunStats) -> None:
        self._client = client
        self._stats = stats

    def complete(self, system: str, user: str, model: str) -> LLMResponse:
        started = time.monotonic()
        try:
            return self._client.complete(system, user, model)
        except LLMFailureBudgetExceeded:
            raise
        except Exception as exc:
            duration = time.monotonic() - started
            print(f"  [LLM] model={model} error={exc} duration_s={duration:.2f}")
            self._stats.record_llm_failure()
            raise


class _FundamentalsFailureAdapter:
    def __init__(self, provider: YFinanceFundamentals, failure_callback=None, timeout: float = 10) -> None:
        self._provider = provider
        self._failure_callback = failure_callback
        self._timeout = timeout
        self._isolated_fetch = IsolatedCall(provider.fetch, timeout)

    def fetch(self, ticker: str):
        started = time.monotonic()
        try:
            return self._isolated_fetch(ticker)
        except Exception as exc:
            duration = time.monotonic() - started
            print(
                f"  [PROVIDER] source=yfinance_fundamentals ticker={ticker} "
                f"error={exc} duration_s={duration:.2f}"
            )
            if self._failure_callback is not None:
                self._failure_callback()
            raise


def _make_alpaca_executor(settings) -> AlpacaPaperExecutor | None:
    provider = (settings.execution_provider or "internal_paper").lower()
    if provider in {"", "internal_paper"}:
        return None
    if provider != "alpaca_paper":
        raise ValueError(f"Unsupported EXECUTION_PROVIDER={settings.execution_provider!r}")
    return AlpacaPaperExecutor(settings)


def _todays_alpaca_order_count(equity_ledger: EquityLedger) -> int:
    today = datetime.now(tz=timezone.utc).date().isoformat()
    return equity_ledger.broker_orders_opened_on(today, provider="alpaca_paper")


_TERMINAL_LOCAL_ORDER_STATUSES = {"canceled", "expired", "rejected", "void", "closed"}


def _has_active_broker_order(row: dict | None) -> bool:
    if row is None:
        return False
    status = row.get("status")
    return status is not None and status not in _TERMINAL_LOCAL_ORDER_STATUSES


def _should_skip_duplicate(existing_order: dict | None) -> bool:
    # ponytail: any prior row with this client_order_id blocks resubmission;
    # Alpaca idempotency on reused IDs after rejection is undefined.
    return existing_order is not None


def _host_resolves(hostname: str) -> bool:
    try:
        socket.getaddrinfo(hostname, 443)
        return True
    except OSError:
        return False


async def run_reconcile_only() -> None:
    """Run broker reconciliation when a reconciler implementation is present."""
    settings = load_config()

    reconcile = None
    for module_name in (
        "equities.execution.reconciler",
        "equities.execution.alpaca_reconciler",
    ):
        try:
            module = __import__(module_name, fromlist=["reconcile_alpaca"])
        except ImportError:
            continue
        reconcile = getattr(module, "reconcile_alpaca", None)
        if reconcile is not None:
            break

    if reconcile is None:
        print("Reconcile-only mode requested, but no Alpaca reconciler is available yet.")
        return

    result = reconcile(settings)
    if inspect.isawaitable(result):
        await result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_once(
    swing_universe: list[Instrument],
    core_universe: list[Instrument],
    no_analyse: bool = False,
    mark_only: bool = False,
    dry_run: bool = False,
    checkpoint: bool = False,
    clear_analysis_checkpoints: bool = False,
) -> None:
    settings = load_config()
    dry_run = dry_run or bool(getattr(settings, "equity_runner_dry_run", False))
    stats = RunStats(
        started_monotonic=time.monotonic(),
        max_runtime_seconds=settings.equity_runner_max_runtime_seconds,
        max_provider_failures=settings.equity_runner_max_provider_failures,
        max_llm_failures=settings.equity_runner_max_llm_failures,
    )
    budget: DailyBudget | None = None

    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    equity_ledger = EquityLedger(data_dir / "equity.db")
    fp_tracker = ForwardPaperTracker(data_dir / "forward_paper.db")
    artifact_store = ResearchArtifactStore(data_dir / "research_artifacts.jsonl")
    artifacts_before_run = len(artifact_store.read_all())
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    checkpoint_store = AnalysisCheckpointStore(data_dir / "equity_analysis_checkpoints.jsonl")
    provider_registry = ProviderRegistry()
    if clear_analysis_checkpoints:
        removed = checkpoint_store.clear_all()
        print(f"Cleared {removed} equity analysis checkpoint(s).")

    def record_provider_failure() -> None:
        stats.record_provider_failure()

    def fallback_mark_price(ticker: str) -> float | None:
        for pos in equity_ledger.open_positions():
            if pos.get("ticker") != ticker:
                continue
            mark_price = pos.get("mark_price")
            if mark_price is not None:
                return float(mark_price)
            entry_price = pos.get("entry_price")
            if entry_price is not None:
                return float(entry_price)
        return None

    price_feed = YFinancePriceFeed(
        timeout=settings.equity_provider_timeout_seconds,
        retries=settings.equity_provider_retries,
    )
    prices = _PriceAdapter(
        price_feed,
        failure_callback=record_provider_failure,
        price_fallback=fallback_mark_price,
    )
    news = CompositeNewsProvider([
        YFinanceNewsProvider(),
        TiingoNewsProvider(),       # no-op if TIINGO_API_KEY absent
        Crawl4AINewsProvider(),     # no-op if crawl4ai not installed
    ], failure_callback=record_provider_failure, registry=provider_registry)
    filings_client = SECEdgarFilings()
    filings_summary = _FilingsSummaryAdapter(filings_client, failure_callback=record_provider_failure)
    llm_client = _LLMFailureCountingClient(ClaudeCodeClient(provider=settings.llm_provider), stats)

    paper = EquityPaperTracker(
        equity_ledger,
        prices,
        price_fallback=fallback_mark_price,
    )
    alpaca_executor = _make_alpaca_executor(settings)

    alerts: TelegramAlerts | None = None
    alerts_disabled = False
    if settings.telegram_bot_token and _host_resolves("api.telegram.org"):
        alerts = TelegramAlerts(settings.telegram_bot_token, settings.telegram_chat_id)
    telegram_alert_mode = str(settings.telegram_alert_mode).strip().lower() or "critical"

    def _telegram_allows(kind: str) -> bool:
        if telegram_alert_mode == "verbose":
            return True
        return kind in {"startup", "error", "stop_loss", "open", "exit"}

    async def _send_alert(text: str) -> None:
        nonlocal alerts_disabled
        if alerts is None or alerts_disabled or not text:
            return
        try:
            await alerts.send(text)
        except Exception as exc:
            print(f"  [ALERT] telegram send failed: {exc}")
            alerts_disabled = True

    try:
        # --- Mark-to-market and fire exits ---
        with _stage(stats, "mark_to_market"):
            pre_mark = {pos["id"]: pos for pos in equity_ledger.open_positions()}
            if dry_run:
                exits = []
                print("  [DRY RUN] skipping mark-and-exit ledger writes")
            else:
                exits = paper.mark_and_check_exits()
            if exits:
                print(f"\n=== {len(exits)} exit(s) fired ===")
                for ex in exits:
                    print(f"  [{ex.position_id}] {ex.reason} @ {ex.exit_price:.2f}")
                    if alerts is not None and ex.position_id in pre_mark:
                        pos = pre_mark[ex.position_id]
                        portfolio_stats = equity_ledger.portfolio_stats()
                        if _telegram_allows("exit"):
                            await _send_alert(alerts.format_equity_exit(
                                ex,
                                ticker=pos["ticker"],
                                entry_price=pos["entry_price"],
                                shares=pos["shares"],
                                portfolio_stats=portfolio_stats,
                            ))
                    if ex.position_id in pre_mark:
                        pos = pre_mark[ex.position_id]
                        if alpaca_executor is not None and pos.get("execution_provider") == "alpaca_paper":
                            try:
                                exit_order = alpaca_executor.sell(pos["ticker"], float(pos["shares"]))
                                print(
                                    f"  ALPACA SELL [{pos['ticker']}] "
                                    f"order_id={exit_order.id} status={exit_order.status}"
                                )
                            except Exception as exc:
                                print(f"  ALPACA SELL FAILED [{pos['ticker']}]: {exc}")
                        fp_tracker.record_exit_for_open_trade(
                            ticker=pos["ticker"],
                            sleeve=pos.get("sleeve"),
                            strategy=pos.get("strategy"),
                            exit_price=ex.exit_price,
                            is_gap_stop=ex.reason == "stop_hit",
                        )

        if mark_only:
            print("Mark-only mode complete.")
            if alerts is not None and _telegram_allows("summary"):
                await _send_alert(alerts.format_equity_portfolio(equity_ledger.portfolio_stats()))
            return

        # --- Macro regime classification ---
        with _stage(stats, "macro_regime"):
            regime_gate = MacroRegimeGate(failure_callback=record_provider_failure)
            regime_snap = regime_gate.classify()
            _vix_str = f"{regime_snap.vix:.1f}" if regime_snap.vix is not None else "n/a"
            _yc_str = f"{regime_snap.yield_curve:.2f}" if regime_snap.yield_curve is not None else "n/a"
            print(f"\n=== Macro Regime: {regime_snap.regime.upper()} | VIX={_vix_str} | Yield curve={_yc_str} ===")

        # --- Thesis health check (nightly) ---
        with _stage(stats, "thesis_health"):
            open_swing = [p for p in equity_ledger.open_positions() if p.get("sleeve") == "swing"]
            if open_swing and not mark_only:
                health_checker = ThesisHealthChecker()
                for health in health_checker.check_all(open_swing, news):
                    print(f"  [HEALTH] {health.ticker}: {health.status} -> {health.action} | {health.reason}")
                    if health.action == "exit" and alerts is not None and _telegram_allows("exit"):
                        await _send_alert(f"Thesis exit signal: {health.ticker} — {health.reason}")

        # --- Thematic concentration check ---
        with _stage(stats, "thematic_concentration"):
            thematic_monitor = ThematicMonitor(max_theme_pct=0.35, capital=settings.bankroll_usd)
            for alert in thematic_monitor.check(equity_ledger.open_positions()):
                print(f"  [THEMATIC] {alert}")

        # --- Swing screen ---
        with _stage(stats, "swing_screen"):
            calendar = YFinanceCalendar()
            event_screen = EventScreen(
                earnings=CalendarAdapter(calendar, failure_callback=record_provider_failure),
                filings=FilingsAdapter(filings_client, failure_callback=record_provider_failure),
            )
            swing_candidates = event_screen.scan(swing_universe)

        with _stage(stats, "relative_strength_screen"):
            rs_scanner = RelativeStrengthScanner(price_feed)
            rs_evidence = rs_scanner.scan(swing_universe)
            coverage = rs_scanner.coverage
            print("\n=== Relative-strength screening coverage ===")
            print("scope=curated_swing_universe (not entire stock market)")
            print(f"total_universe={coverage.total}")
            print(f"successfully_screened={coverage.screened}")
            print(f"skipped_failed={len(coverage.failed)}")
            for ticker, reason in coverage.failed.items():
                print(f"  ticker={ticker} reason={reason}")
            enriched_candidates = []
            for candidate in swing_candidates:
                evidence = rs_evidence.get(candidate.instrument.ticker)
                if evidence is None:
                    enriched_candidates.append(candidate)
                    continue
                enriched_candidates.append(
                    replace(
                        candidate,
                        evidence=f"{candidate.evidence} | Technicals: {evidence.evidence}",
                    )
                )
                print(f"  [RS] {candidate.instrument.ticker}: {evidence.evidence}")
            swing_candidates = enriched_candidates

        # --- Politician disclosure screen (off by default) ---
        if getattr(settings, "politician_signal_enabled", False):
            with _stage(stats, "politician_screen"):
                pol_sources = [
                    HouseClerkDisclosureProvider(
                        lookback_days=settings.politician_lookback_days,
                        max_pdfs=settings.politician_max_pdfs,
                        timeout=settings.equity_provider_timeout_seconds,
                    )
                ]
                if getattr(settings, "politician_include_senate", False):
                    pol_sources.append(SenateEFDDisclosureProvider(
                        lookback_days=settings.politician_lookback_days,
                        max_reports=settings.politician_max_pdfs,
                        timeout=settings.equity_provider_timeout_seconds,
                    ))
                if getattr(settings, "politician_include_executive", False):
                    pol_sources.append(ExecutiveDisclosureProvider(
                        lookback_days=settings.politician_lookback_days,
                        timeout=settings.equity_provider_timeout_seconds,
                    ))
                pol_provider = CompositeDisclosureProvider(pol_sources)
                pol_candidates = PoliticianScreen(pol_provider).scan(swing_universe)
                for c in pol_candidates:
                    print(f"  [POL] {c.instrument.ticker}: {c.evidence} (urgency={c.urgency:.2f})")
                swing_candidates = swing_candidates + pol_candidates

        # --- Core screen ---
        with _stage(stats, "core_screen"):
            fundamentals_provider = _FundamentalsFailureAdapter(
                YFinanceFundamentals(),
                failure_callback=record_provider_failure,
                timeout=settings.equity_provider_timeout_seconds,
            )
            quality_screen = QualityScreen(fundamentals_provider)
            core_candidates = quality_screen.scan(core_universe)

        print(f"\n=== Swing candidates: {len(swing_candidates)} ===")
        for c in swing_candidates:
            print(f"  [{c.event_type.value}] {c.instrument.ticker}: {c.evidence} (urgency={c.urgency:.2f})")

        print(f"\n=== Core candidates: {len(core_candidates)} ===")
        for c in core_candidates:
            print(f"  [{c.instrument.ticker}] score={c.score:.3f}: {c.evidence}")

        # --- Inflection screen ---
        with _stage(stats, "inflection_screen"):
            inflection_screen = InflectionScanner(fundamentals_provider)
            inflection_candidates = inflection_screen.scan(swing_universe)
            print(f"\n=== Inflection candidates: {len(inflection_candidates)} ===")
            for c in inflection_candidates:
                print(f"  [{c.ticker}] ~{c.quarters_to_profit}q to profit | {c.evidence}")

        if no_analyse:
            print("Screen-only mode complete.")
            return

        # --- VIX regime gate ---
        with _stage(stats, "vix_gate"):
            vix_gate = VIXRegimeGate(threshold=30.0)
            entries_allowed, current_vix = vix_gate.allow_new_entries()
            if current_vix is not None:
                print(f"\nVIX: {current_vix:.1f} | entries_allowed={entries_allowed}")
            if not entries_allowed:
                print(f"VIX={current_vix:.1f} > 30 — blocking new entries. Running mark-to-market only.")
                if _telegram_allows("summary"):
                    await _send_alert(f"VIX={current_vix:.1f} — new entries blocked today.")
                return

        # --- Scan summary alert ---
        if alerts is not None and _telegram_allows("summary"):
            analyst_count = min(len(swing_candidates), 5)
            await _send_alert(alerts.format_equity_scan(swing_candidates, core_candidates, analyst_count))

        # --- Analyst stage (Codex CLI by default; OpenAI/Claude are explicit fallbacks) ---
        budget = DailyBudget(daily_limit_usd=999.0)
        # Smart-money 13F context (portfolio-level, fetched once per run; off by default)
        smart_money_block = ""
        if getattr(settings, "smart_money_13f_enabled", False):
            with _stage(stats, "smart_money_13f"):
                summaries = []
                for pair in settings.smart_money_ciks.split(","):
                    cik, _, name = pair.strip().partition(":")
                    if not cik.strip():
                        continue
                    summary = Fund13FProvider(cik=cik.strip(), fund_name=name.strip()).context_summary()
                    if summary and "Failed to fetch" not in summary and "No holdings" not in summary:
                        summaries.append(summary)
                        print(f"  [13F] {name.strip() or cik.strip()}: loaded")
                smart_money_block = "\n\n".join(summaries)

        analyst = EquityAnalyst(
            llm=llm_client,
            prices=prices,
            news=news,
            filings=filings_summary,
            fundamentals=fundamentals_provider,
            budget=budget,
            max_candidates=5,
            max_price_age_days=settings.equity_max_price_age_days,
            artifact_store=artifact_store,
            checkpoint_store=checkpoint_store,
            checkpoints_enabled=checkpoint,
            smart_money_block=smart_money_block,
        )

        with _stage(stats, "analyst"):
            swing_recommendations = analyst.analyse(
                swing_candidates,
                regime=regime_snap.regime,
                vix=regime_snap.vix,
                yield_curve=regime_snap.yield_curve,
            )

        # --- Core DCA analyst (risk-officer check before accumulating) ---
        core_analyst = CoreDCAAnalyst(
            llm=llm_client,
            prices=prices,
            news=news,
            fundamentals=fundamentals_provider,
            budget=budget,
            max_candidates=4,
        )
        with _stage(stats, "core_analyst"):
            core_recommendations = core_analyst.analyse(core_candidates)

        all_recommendations = swing_recommendations + core_recommendations

        # --- Risk kernel + paper open ---
        kernel = RiskKernel(
            capital=settings.bankroll_usd,
            risk_pct=settings.equity_risk_pct,
            max_positions=settings.equity_max_positions,
            max_name_pct=settings.equity_max_name_pct,
            max_sector_pct=settings.equity_max_sector_pct,
            daily_loss_limit_pct=settings.equity_daily_loss_limit_pct,
            drawdown_limit_pct=settings.equity_drawdown_limit_pct,
            state_path=Path("data/kernel_state.json"),
        )
        open_positions = equity_ledger.open_positions()
        sector_lookup: dict[str, str] = {}

        def sector_for(ticker: str) -> str:
            if ticker in sector_lookup:
                return sector_lookup[ticker]
            try:
                sector_lookup[ticker] = fundamentals_provider.fetch(ticker).sector
            except (RuntimeError, TimeoutError):
                raise
            except Exception as exc:
                print(f"  [PROVIDER] source=yfinance_fundamentals ticker={ticker} error={exc}")
                sector_lookup[ticker] = ""
            return sector_lookup[ticker]

        for pos in open_positions:
            ticker = str(pos.get("ticker", ""))
            if ticker and not pos.get("sector"):
                pos["sector"] = sector_for(ticker)
        for rec in all_recommendations:
            sector_for(rec.instrument.ticker)

        today = datetime.now(tz=timezone.utc).date().isoformat()
        portfolio_stats = equity_ledger.portfolio_stats()
        current_equity = (
            settings.bankroll_usd
            + float(portfolio_stats.get("realized_pnl", 0.0))
            + float(portfolio_stats.get("unrealized_pnl", 0.0))
        )
        deployable_equity = current_equity - equity_ledger.pending_notional()
        today_realized_loss = equity_ledger.realized_pnl_on(today)

        with _stage(stats, "risk_and_execution"):
            print(f"\n=== Swing recommendations: {len(swing_recommendations)} ===")
            print(f"=== Core DCA recommendations: {len(core_recommendations)} ===")
            for rec in all_recommendations:
                stats.check_runtime()
                sized = kernel.approve(
                    rec,
                    open_positions,
                    today_realized_loss=today_realized_loss,
                    current_equity=deployable_equity,
                    sector_lookup=sector_lookup,
                )
                if not sized.approved:
                    print(f"  REJECTED [{rec.instrument.ticker}] ({rec.sleeve.value}): {sized.rejection_reason}")
                    artifact_store.append(risk_decision_artifact(
                        rec, decision="rejected", rejection_reason=sized.rejection_reason or "risk_kernel_rejected",
                        stage="risk", shares=sized.shares,
                        risk_metrics={"open_positions": len(open_positions), "current_equity": current_equity},
                    ))
                    continue

                order_notional = sized.shares * rec.entry
                if order_notional > settings.max_order_usd:
                    reason = (
                        f"order_notional=${order_notional:.2f}_exceeds_max_order_usd=${settings.max_order_usd:.2f}"
                    )
                    print(f"  REJECTED [{rec.instrument.ticker}] ({rec.sleeve.value}): {reason}")
                    artifact_store.append(risk_decision_artifact(
                        rec, decision="rejected", rejection_reason=reason, stage="notional",
                        shares=sized.shares, notional=order_notional,
                        risk_metrics={"max_order_usd": settings.max_order_usd},
                    ))
                    continue
                if alpaca_executor is not None and _todays_alpaca_order_count(equity_ledger) >= settings.max_daily_order_count:
                    reason = f"max_daily_order_count={settings.max_daily_order_count}_reached"
                    print(f"  REJECTED [{rec.instrument.ticker}] ({rec.sleeve.value}): {reason}")
                    artifact_store.append(risk_decision_artifact(
                        rec, decision="rejected", rejection_reason=reason, stage="daily_cap",
                        shares=sized.shares, notional=order_notional,
                    ))
                    continue

                if dry_run:
                    print(
                        f"  [DRY RUN] would_open [{rec.instrument.ticker}] "
                        f"shares={sized.shares:.4f} entry={rec.entry:.2f} notional=${order_notional:.2f}"
                    )
                    continue

                if alpaca_executor is not None:
                    client_order_id = client_order_id_for(rec, sized.shares)
                    existing_order = equity_ledger.position_by_broker_client_order_id(client_order_id)
                    if _should_skip_duplicate(existing_order):
                        print(
                            f"  SKIPPED [{rec.instrument.ticker}] duplicate_client_order_id="
                            f"{client_order_id} status={existing_order.get('status')}"
                        )
                        continue
                    try:
                        order = alpaca_executor.buy(
                            rec,
                            sized.shares,
                            client_order_id=client_order_id,
                            max_notional=settings.max_order_usd,
                        )
                    except Exception as exc:
                        print(f"  ALPACA REJECTED [{rec.instrument.ticker}]: {exc}")
                        artifact_store.append(risk_decision_artifact(
                            rec, decision="rejected", rejection_reason=f"alpaca_error: {exc}",
                            stage="broker", shares=sized.shares, notional=order_notional,
                        ))
                        continue
                    local_status = "open" if order.status == "filled" else (
                        "partially_filled" if order.status == "partially_filled" else "submitted"
                    )
                    filled_shares = order.filled_qty if order.filled_qty > 0 else sized.shares
                    ledger_entry_price = order.filled_avg_price if order.filled_avg_price is not None else rec.entry
                    position_id = equity_ledger.open_position(
                        rec,
                        filled_shares,
                        ledger_entry_price,
                        datetime.now(tz=timezone.utc),
                        mode="paper",
                        strategy="equity_analyst",
                        execution_provider="alpaca_paper",
                        broker_order_id=order.id,
                        broker_client_order_id=order.client_order_id or client_order_id,
                        broker_order_status=order.status,
                        sector=sector_lookup.get(rec.instrument.ticker, ""),
                        status=local_status,
                    )
                    fill = PaperFill(
                        position_id=position_id,
                        ticker=rec.instrument.ticker,
                        shares=filled_shares,
                        entry_price=ledger_entry_price,
                        sleeve=rec.sleeve.value,
                    )
                    print(
                        f"  ALPACA BUY [{rec.instrument.ticker}] "
                        f"order_id={order.id} client_order_id={order.client_order_id or client_order_id} "
                        f"status={order.status}"
                    )
                    # Record in forward-paper tracker immediately (even if not yet filled)
                    # so pending orders are counted toward the 100-trade promotion gate
                    fp_tracker.record_entry(
                        ticker=rec.instrument.ticker,
                        sleeve=rec.sleeve.value,
                        entry_price=fill.entry_price,
                        shares=fill.shares,
                        strategy="equity_analyst",
                    )
                    if order.status != "filled":
                        print(
                            f"  PENDING BROKER ORDER [{rec.instrument.ticker}] "
                            f"status={order.status}; recorded forward-paper entry at intended price"
                        )
                        open_positions = equity_ledger.open_positions()
                        continue
                else:
                    position_id = equity_ledger.open_position(
                        rec,
                        sized.shares,
                        rec.entry,
                        datetime.now(tz=timezone.utc),
                        mode="paper",
                        strategy="equity_analyst",
                        sector=sector_lookup.get(rec.instrument.ticker, ""),
                    )
                    fill = PaperFill(
                        position_id=position_id,
                        ticker=rec.instrument.ticker,
                        shares=sized.shares,
                        entry_price=rec.entry,
                        sleeve=rec.sleeve.value,
                    )
                    fp_tracker.record_entry(
                        ticker=rec.instrument.ticker,
                        sleeve=rec.sleeve.value,
                        entry_price=fill.entry_price,
                        shares=fill.shares,
                        strategy="equity_analyst",
                    )
                artifact_store.append(risk_decision_artifact(
                    rec, decision="approved", stage="risk",
                    shares=fill.shares, notional=fill.shares * fill.entry_price,
                ))
                if rec.sleeve.value == "core":
                    print(
                        f"  DCA OPEN [{rec.instrument.ticker}] "
                        f"shares={sized.shares:.4f} entry={rec.entry:.2f} (no stop)"
                    )
                else:
                    print(
                        f"  PAPER OPEN [{rec.instrument.ticker}] "
                        f"shares={sized.shares:.4f} entry={rec.entry:.2f} "
                        f"stop={rec.stop_loss:.2f} tp={rec.take_profit:.2f}"
                    )
                if alerts is not None and _telegram_allows("open"):
                    await _send_alert(alerts.format_equity_open(rec, fill))
                open_positions = equity_ledger.open_positions()

        # --- Portfolio summary ---
        if alerts is not None and _telegram_allows("summary"):
            await _send_alert(alerts.format_equity_portfolio(equity_ledger.portfolio_stats()))
    finally:
        _print_run_summary(stats, budget, provider_registry=provider_registry)
        if alerts is not None and _telegram_allows("summary"):
            await _send_alert(alerts.format_run_summary(stats, budget, provider_registry))
        equity_ledger.close()
        fp_tracker.close()

        try:
            new_artifacts = artifact_store.read_all()[artifacts_before_run:]
            manifest = build_run_manifest(
                config_snapshot=settings_snapshot(settings),
                prompt_versions_used=sorted({a.prompt_version for a in new_artifacts}),
                model_ids=sorted({a.llm_model for a in new_artifacts if a.llm_model}),
                source_ids_fetched=sorted({s.id for a in new_artifacts for s in a.sources}),
                run_id=run_id,
            )
            with open(data_dir / "run_manifests.jsonl", "a") as f:
                f.write(json.dumps(manifest.as_record()) + "\n")
        except Exception as exc:
            print(f"WARNING: failed to write run manifest: {exc}")


def main() -> None:
    from scripts.preflight import run_preflight

    preflight = run_preflight(load_config())
    if not preflight.ok:
        print("PREFLIGHT FAILED:")
        for failure in preflight.failures:
            print(f"  - {failure}")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Equities paper runner")
    parser.add_argument("--no-analyse", action="store_true", help="Screen only; skip LLM analyst")
    parser.add_argument("--mark-only", action="store_true", help="Mark-to-market + exits only")
    parser.add_argument("--reconcile-only", action="store_true", help="Broker reconciliation only")
    parser.add_argument("--dry-run", action="store_true", help="Run without ledger, forward-tracker, or broker writes")
    parser.add_argument("--checkpoint", action="store_true", help="Reuse validated LLM stage checkpoints")
    parser.add_argument(
        "--clear-analysis-checkpoints",
        action="store_true",
        help="Clear saved equity analysis checkpoints before running",
    )
    args = parser.parse_args()

    if args.reconcile_only:
        asyncio.run(run_reconcile_only())
        return

    asyncio.run(
        run_once(
            DEFAULT_SWING_UNIVERSE,
            DEFAULT_CORE_UNIVERSE,
            no_analyse=args.no_analyse,
            mark_only=args.mark_only,
            dry_run=args.dry_run,
            checkpoint=args.checkpoint,
            clear_analysis_checkpoints=args.clear_analysis_checkpoints,
        )
    )


if __name__ == "__main__":
    main()
