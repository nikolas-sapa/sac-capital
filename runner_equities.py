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
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from core.alerts.telegram import TelegramAlerts
from core.assets.instrument import CapTier, Instrument
from equities.strategy import Recommendation, Sleeve
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
from equities.data.truth_social import TruthSocialNewsProvider
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
from equities.risk.rebalance import compute_trims
from equities.risk.correlation import CorrelationChecker
from equities.risk.news_guard import NewsGuard
from equities.risk.vol_target import vol_target_shares
from equities.data.technicals import vol_20d_ann_pct
from equities.killgate.thesis_health import ThesisHealthChecker
from equities.pit import assert_point_in_time, LookAheadError
from equities.research.artifacts import risk_decision_artifact
from equities.signal_stats import signal_stats_line, update_signal_stats
from equities.research.run_manifest import build_run_manifest, settings_snapshot
from equities.research.store import ResearchArtifactStore
from equities.screen.inflection_screen import InflectionScanner
from equities.screen.relative_strength import RelativeStrengthScanner
from equities.screen.thematic_monitor import ThematicMonitor
from equities.screen.event_screen import (
    CalendarAdapter,
    CandidateEvent,
    EventScreen,
    EventType,
    FilingsAdapter,
)
from equities.screen.quality_screen import QualityScreen
from equities.screen.politician_screen import PoliticianScreen
from equities.screen.supply_chain_lag_screen import (
    SupplyChainLagCandidate,
    SupplyChainLagScreen,
)
from equities.data.house_clerk_disclosures import HouseClerkDisclosureProvider
from equities.data.senate_efd_disclosures import SenateEFDDisclosureProvider
from equities.data.executive_disclosures import ExecutiveDisclosureProvider
from equities.data.composite_disclosures import CompositeDisclosureProvider
from equities.data.fund_13f import Fund13FProvider

# ---------------------------------------------------------------------------
# Default universe (extend via --universe flag or editing this list)
# ---------------------------------------------------------------------------

# Fraction of the swing universe that must have usable technical history before
# the hard tech gate is trusted. Below this the feed is degraded, and a gate
# that cannot evaluate must not approve — see relative_strength_screen stage.
_MIN_TECH_COVERAGE = 0.70
_TECH_COVERAGE_RETRY_SLEEP_S = 20.0


def _tech_coverage_ok(screened: int, total: int) -> bool:
    """True when enough of the universe has technicals to trust the gate."""
    if not total:
        return True
    return screened / total >= _MIN_TECH_COVERAGE


def _apply_tech_gate(
    candidates: list[CandidateEvent],
    rs_evidence: dict,
    coverage,
    hard_gate: bool,
    *,
    label: str = "TECH GATE",
) -> list[CandidateEvent]:
    """Drop candidates failing the technical gate; annotate survivors.

    Shared by every screen whose entries should be timing-checked. The
    supply-chain-lag screen deliberately does NOT use this — laggards fail a
    momentum gate by definition (see its call site).
    """
    kept: list[CandidateEvent] = []
    for candidate in candidates:
        ticker = candidate.instrument.ticker
        evidence = rs_evidence.get(ticker)
        if evidence is None:
            # No evidence because the data failed → drop (fail closed).
            # No evidence because the name is genuinely too young (recent
            # IPO) → keep; that is a property of the stock, not an outage.
            failure = coverage.failed.get(ticker)
            if not _keep_candidate_without_technicals(failure, hard_gate):
                print(f"  [{label}] {ticker}: dropped (no technicals: {failure})")
                continue
            kept.append(candidate)
            continue
        if hard_gate:
            ok, gate_reason = _passes_tech_gate(evidence)
            if not ok:
                print(f"  [{label}] {ticker}: dropped ({gate_reason})")
                continue
        kept.append(
            replace(
                candidate,
                evidence=f"{candidate.evidence} | Technicals: {evidence.evidence}",
            )
        )
        print(f"  [RS] {ticker}: {evidence.evidence}")
    return kept


def _keep_candidate_without_technicals(failure: str | None, hard_gate: bool) -> bool:
    """Whether a candidate with no technical evidence may still proceed.

    A data outage must fail closed (drop it). A genuinely short price history
    is a property of the stock, not an outage, so recent IPOs stay eligible.
    """
    if not hard_gate:
        return True
    if failure and failure != "insufficient history":
        return False
    return True

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

    # --- Breadth expansion 2026-08-04 -------------------------------------
    # Every ticker below was validated against yfinance (live price + market
    # cap) and SEC EDGAR (CIK resolves, so the filings screen can see it).
    # Cap tier assigned from real market cap: LARGE >=$100B, MID >=$12B.
    # All land SMALL/MID, i.e. all are eligible for the swing event screen.

    # Neocloud / AI datacenter
    Instrument("IREN",  "IREN Limited",               "NASDAQ", CapTier.MID),
    Instrument("CRWV",  "CoreWeave",                  "NASDAQ", CapTier.MID),
    Instrument("CIFR",  "Cipher Mining",              "NASDAQ", CapTier.SMALL),
    Instrument("WULF",  "TeraWulf",                   "NASDAQ", CapTier.SMALL),
    Instrument("APLD",  "Applied Digital",            "NASDAQ", CapTier.SMALL),
    Instrument("GLXY",  "Galaxy Digital",             "NASDAQ", CapTier.SMALL),
    # Quantum
    Instrument("IONQ",  "IonQ",                       "NYSE",   CapTier.MID),
    Instrument("RGTI",  "Rigetti Computing",          "NASDAQ", CapTier.SMALL),
    Instrument("QBTS",  "D-Wave Quantum",             "NASDAQ", CapTier.SMALL),
    Instrument("QUBT",  "Quantum Computing Inc",      "NASDAQ", CapTier.SMALL),
    # Nuclear / SMR / uranium
    Instrument("OKLO",  "Oklo",                       "NYSE",   CapTier.SMALL),
    Instrument("SMR",   "NuScale Power",              "NYSE",   CapTier.SMALL),
    Instrument("LEU",   "Centrus Energy",             "NYSE",   CapTier.SMALL),
    Instrument("BWXT",  "BWX Technologies",           "NYSE",   CapTier.MID),
    Instrument("NNE",   "Nano Nuclear Energy",        "NASDAQ", CapTier.SMALL),
    Instrument("CCJ",   "Cameco",                     "NYSE",   CapTier.MID),
    Instrument("TLN",   "Talen Energy",               "NASDAQ", CapTier.MID),
    # Energy storage / solar infrastructure
    Instrument("FLNC",  "Fluence Energy",             "NASDAQ", CapTier.SMALL),
    Instrument("NXT",   "Nextracker",                 "NASDAQ", CapTier.MID),
    Instrument("ENPH",  "Enphase Energy",             "NASDAQ", CapTier.SMALL),
    Instrument("ARRY",  "Array Technologies",         "NASDAQ", CapTier.SMALL),
    Instrument("SEDG",  "SolarEdge Technologies",     "NASDAQ", CapTier.SMALL),
    # Space / drones / defense tech
    Instrument("PL",    "Planet Labs",                "NYSE",   CapTier.SMALL),
    Instrument("RCAT",  "Red Cat Holdings",           "NASDAQ", CapTier.SMALL),
    Instrument("DRS",   "Leonardo DRS",               "NASDAQ", CapTier.MID),
    Instrument("RDW",   "Redwire",                    "NYSE",   CapTier.SMALL),
    # Robotics / automation
    Instrument("SYM",   "Symbotic",                   "NASDAQ", CapTier.MID),
    Instrument("SERV",  "Serve Robotics",             "NASDAQ", CapTier.SMALL),
    Instrument("TER",   "Teradyne",                   "NASDAQ", CapTier.MID),
    Instrument("ROK",   "Rockwell Automation",        "NYSE",   CapTier.MID),
    # Semi equipment & components
    Instrument("AEHR",  "Aehr Test Systems",          "NASDAQ", CapTier.SMALL),
    Instrument("ACLS",  "Axcelis Technologies",       "NASDAQ", CapTier.SMALL),
    Instrument("UCTT",  "Ultra Clean Holdings",       "NASDAQ", CapTier.SMALL),
    Instrument("CAMT",  "Camtek",                     "NASDAQ", CapTier.SMALL),
    Instrument("NVMI",  "Nova Ltd",                   "NASDAQ", CapTier.MID),
    Instrument("CRDO",  "Credo Technology",           "NASDAQ", CapTier.MID),
    Instrument("MTSI",  "MACOM Technology",           "NASDAQ", CapTier.MID),
    Instrument("SITM",  "SiTime",                     "NASDAQ", CapTier.MID),
    Instrument("POWI",  "Power Integrations",         "NASDAQ", CapTier.SMALL),
    Instrument("PI",    "Impinj",                     "NASDAQ", CapTier.SMALL),
    Instrument("LSCC",  "Lattice Semiconductor",      "NASDAQ", CapTier.MID),
    Instrument("RMBS",  "Rambus",                     "NASDAQ", CapTier.SMALL),
    Instrument("ALGM",  "Allegro MicroSystems",       "NASDAQ", CapTier.SMALL),
    Instrument("PENG",  "Penguin Solutions",          "NASDAQ", CapTier.SMALL),
    # Biotech / GLP-1 / genomics
    Instrument("VKTX",  "Viking Therapeutics",        "NASDAQ", CapTier.SMALL),
    Instrument("CRSP",  "CRISPR Therapeutics",        "NASDAQ", CapTier.SMALL),
    Instrument("NTLA",  "Intellia Therapeutics",      "NASDAQ", CapTier.SMALL),
    Instrument("BEAM",  "Beam Therapeutics",          "NASDAQ", CapTier.SMALL),
    Instrument("RXRX",  "Recursion Pharmaceuticals",  "NASDAQ", CapTier.SMALL),
    Instrument("ALNY",  "Alnylam Pharmaceuticals",    "NASDAQ", CapTier.MID),
    # Fintech / crypto-adjacent
    Instrument("UPST",  "Upstart Holdings",           "NASDAQ", CapTier.SMALL),
    Instrument("DAVE",  "Dave Inc",                   "NASDAQ", CapTier.SMALL),
    Instrument("OSCR",  "Oscar Health",               "NYSE",   CapTier.SMALL),
    Instrument("LMND",  "Lemonade",                   "NYSE",   CapTier.SMALL),
    Instrument("CRCL",  "Circle Internet Group",      "NYSE",   CapTier.MID),
    Instrument("MSTR",  "Strategy Inc",               "NASDAQ", CapTier.MID),
    Instrument("MARA",  "MARA Holdings",              "NASDAQ", CapTier.SMALL),
    Instrument("RIOT",  "Riot Platforms",             "NASDAQ", CapTier.SMALL),
    # Internet / media
    Instrument("RDDT",  "Reddit",                     "NYSE",   CapTier.MID),
    Instrument("ROKU",  "Roku",                       "NASDAQ", CapTier.MID),
    Instrument("PINS",  "Pinterest",                  "NYSE",   CapTier.MID),
    Instrument("SNAP",  "Snap",                       "NYSE",   CapTier.SMALL),
    Instrument("SPOT",  "Spotify Technology",         "NYSE",   CapTier.MID),
    # AI software
    Instrument("BBAI",  "BigBear.ai",                 "NYSE",   CapTier.SMALL),
    Instrument("INOD",  "Innodata",                   "NASDAQ", CapTier.SMALL),
    Instrument("PATH",  "UiPath",                     "NYSE",   CapTier.SMALL),
    Instrument("DOCN",  "DigitalOcean Holdings",      "NYSE",   CapTier.MID),
    Instrument("ESTC",  "Elastic NV",                 "NYSE",   CapTier.SMALL),
    Instrument("GTLB",  "GitLab",                     "NASDAQ", CapTier.SMALL),

    # --- Politician-disclosure coverage 2026-08-05 ------------------------
    # Names congress/executives actually bought that the universe could not
    # see. The politician screen intersects disclosures with this list, so an
    # untracked ticker is invisible no matter how many filings it has: only
    # 15 of 123 recent buys were in scope before this. Validated against
    # yfinance (live price + market cap) and SEC EDGAR (CIK resolves).
    Instrument("ABT",   "Abbott Laboratories",              "NYSE",   CapTier.LARGE),
    Instrument("ACN",   "Accenture",                        "NYSE",   CapTier.LARGE),
    Instrument("ADP",   "Automatic Data Processing",        "NASDAQ", CapTier.LARGE),
    Instrument("AMAT",  "Applied Materials",                "NASDAQ", CapTier.LARGE),
    Instrument("ANET",  "Arista Networks",                  "NYSE",   CapTier.LARGE),
    Instrument("JNJ",   "Johnson & Johnson",                "NYSE",   CapTier.LARGE),
    Instrument("BEP",   "Brookfield Renewable Partners",    "NYSE",   CapTier.MID),
    Instrument("BSX",   "Boston Scientific",                "NYSE",   CapTier.MID),
    Instrument("CHRW",  "C.H. Robinson Worldwide",          "NASDAQ", CapTier.MID),
    Instrument("CMCSA", "Comcast",                          "NASDAQ", CapTier.MID),
    Instrument("EA",    "Electronic Arts",                  "NASDAQ", CapTier.MID),
    Instrument("FE",    "FirstEnergy",                      "NYSE",   CapTier.MID),
    Instrument("FWONK", "Liberty Media Formula One",        "NASDAQ", CapTier.MID),
    Instrument("GIS",   "General Mills",                    "NYSE",   CapTier.MID),
    Instrument("HCA",   "HCA Healthcare",                   "NYSE",   CapTier.MID),
    Instrument("ICE",   "Intercontinental Exchange",        "NYSE",   CapTier.MID),
    Instrument("LHX",   "L3Harris Technologies",            "NYSE",   CapTier.MID),
    Instrument("LPLA",  "LPL Financial Holdings",           "NASDAQ", CapTier.MID),
    Instrument("MCHP",  "Microchip Technology",             "NASDAQ", CapTier.MID),
    Instrument("MCK",   "McKesson",                         "NYSE",   CapTier.MID),
    Instrument("MLM",   "Martin Marietta Materials",        "NYSE",   CapTier.MID),
    Instrument("MNST",  "Monster Beverage",                 "NASDAQ", CapTier.MID),
    Instrument("PPG",   "PPG Industries",                   "NYSE",   CapTier.MID),
    Instrument("TDG",   "TransDigm Group",                  "NYSE",   CapTier.MID),
    Instrument("TEL",   "TE Connectivity",                  "NYSE",   CapTier.MID),
    Instrument("TXRH",  "Texas Roadhouse",                  "NASDAQ", CapTier.MID),
    Instrument("VRSK",  "Verisk Analytics",                 "NASDAQ", CapTier.MID),
    Instrument("ZTS",   "Zoetis",                           "NYSE",   CapTier.MID),
    Instrument("BOOT",  "Boot Barn Holdings",               "NYSE",   CapTier.SMALL),
    Instrument("CDRE",  "Cadre Holdings",                   "NYSE",   CapTier.SMALL),
    Instrument("CECO",  "CECO Environmental",               "NASDAQ", CapTier.SMALL),
    Instrument("CYTK",  "Cytokinetics",                     "NASDAQ", CapTier.SMALL),
    Instrument("DSGX",  "Descartes Systems Group",          "NASDAQ", CapTier.SMALL),
    Instrument("ESAB",  "ESAB Corporation",                 "NYSE",   CapTier.SMALL),
    Instrument("FSV",   "FirstService",                     "NASDAQ", CapTier.SMALL),
    Instrument("HQY",   "HealthEquity",                     "NASDAQ", CapTier.SMALL),
    Instrument("JKHY",  "Jack Henry & Associates",          "NASDAQ", CapTier.SMALL),
    Instrument("LTH",   "Life Time Group Holdings",         "NYSE",   CapTier.SMALL),
    Instrument("MTN",   "Vail Resorts",                     "NYSE",   CapTier.SMALL),
    Instrument("TCBI",  "Texas Capital Bancshares",         "NASDAQ", CapTier.SMALL),
]


DEFAULT_CORE_UNIVERSE: list[Instrument] = [
    # Quality large-caps — scored on fundamentals (margins, PE, growth)
    Instrument("MSFT",  "Microsoft",       "NASDAQ", CapTier.LARGE),
    Instrument("AAPL",  "Apple",           "NASDAQ", CapTier.LARGE),
    Instrument("GOOGL", "Alphabet",        "NASDAQ", CapTier.LARGE),
    Instrument("META",  "Meta Platforms",  "NASDAQ", CapTier.LARGE),
    Instrument("NVDA",  "NVIDIA",          "NASDAQ", CapTier.LARGE),
    Instrument("AMZN",  "Amazon",          "NASDAQ", CapTier.LARGE),
    # Recent listing: ~36 bars of history, so momentum screens cannot score it
    # yet. Core is fundamentals-scored, which is why it belongs here and not in
    # the swing universe (which is SMALL/MID only in any case).
    Instrument("SPCX",  "Space Exploration Technologies", "NASDAQ", CapTier.LARGE),
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

    def closes(self, ticker: str) -> list[float] | None:
        """Return list of closing prices from cached price series.

        Reuses the cached PriceSeries from _latest_series to avoid new fetches.
        """
        try:
            series = self._latest_series(ticker)
            return series.closes if series.bars else None
        except Exception:
            return None

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


def _should_skip_duplicate(existing_order: dict | None) -> bool:
    # ponytail: any prior row with this client_order_id blocks resubmission;
    # Alpaca idempotency on reused IDs after rejection is undefined.
    return existing_order is not None


_TERMINAL_FAILURE_STATUSES = {"rejected", "canceled", "cancelled", "expired", "suspended", "stopped"}


def _local_status_for(broker_status: str) -> str:
    """Map broker status to local order status.

    Terminal failure statuses map to 'rejected'. Filled orders map to 'open'.
    Partially filled orders preserve their status. All other statuses map to 'submitted'.
    Unknown statuses trigger a warning.
    """
    if broker_status == "filled":
        return "open"
    if broker_status == "partially_filled":
        return "partially_filled"
    if broker_status in _TERMINAL_FAILURE_STATUSES:
        return "rejected"
    if broker_status not in {"new", "accepted", "pending_new", "accepted_for_bidding"}:
        print(f"  WARNING unknown broker status '{broker_status}', treating as submitted")
    return "submitted"


def _host_resolves(hostname: str) -> bool:
    try:
        socket.getaddrinfo(hostname, 443)
        return True
    except OSError:
        return False


def _apply_sizing_verdict(rec) -> tuple:
    """Apply size_verdict to recommendation, return (adjusted_rec, decision).

    decision: "proceed" for "full"/"half", "skip" for "skip"
    Halves size_pct for "half" verdict.
    """
    verdict = getattr(rec, "size_verdict", "full")
    if verdict == "skip":
        return rec, "skip"

    if verdict == "half":
        rec_halved = replace(rec, size_pct=rec.size_pct * 0.5)
        return rec_halved, "proceed"

    return rec, "proceed"


def _passes_tech_gate(evidence) -> tuple[bool, str]:
    """Hard technical gate: post-spike chases and broken trends never reach the LLM.

    MAX-effect evidence: buying post-spike names is the counterparty's trade.
    Missing evidence passes — the gate only acts on affirmative red flags.
    """
    if evidence is None:
        return True, ""
    if getattr(evidence, "do_not_chase", False):
        return False, "do_not_chase"
    if not getattr(evidence, "trend_ok", True):
        return False, "trend_fail"
    return True, ""


def _lag_candidate_to_event(
    c: SupplyChainLagCandidate,
    universe: list[Instrument] | None = None,
) -> CandidateEvent:
    """Convert a supply-chain-lag candidate into the swing pipeline's CandidateEvent."""
    instrument = None
    for inst in universe or DEFAULT_SWING_UNIVERSE:
        if inst.ticker == c.ticker:
            instrument = inst
            break
    if instrument is None:
        instrument = Instrument(c.ticker, c.ticker, "NASDAQ", CapTier.MID)

    lag_1y = c.features.get("lag_1y")
    bottleneck = c.features.get("bottleneck_score", c.features.get("min_bottleneck_score"))
    lag_part = f"lag1y={lag_1y:.0f}% " if isinstance(lag_1y, int | float) else ""
    bottleneck_part = f"bottleneck={bottleneck:.2f} " if isinstance(bottleneck, int | float) else ""
    evidence = f"{c.thesis} [{lag_part}{bottleneck_part}opp={c.opportunity_score:.2f}]"
    return CandidateEvent(
        instrument=instrument,
        event_type=EventType.SUPPLY_CHAIN_LAG,
        evidence=evidence,
        urgency=round(min(1.0, c.opportunity_score), 4),
    )


def _dedup_union(*lists: list[Instrument]) -> list[Instrument]:
    """Deduped union of instrument lists, preserving order (first occurrence wins)."""
    seen: set[str] = set()
    result: list[Instrument] = []
    for lst in lists:
        for inst in lst:
            if inst.ticker in seen:
                continue
            seen.add(inst.ticker)
            result.append(inst)
    return result


def _execute_thesis_exit(health, pos, equity_ledger, fp_tracker, alpaca_executor, now) -> bool:
    """Close a position whose thesis the health checker invalidated.

    Ledger close is authoritative and never blocked by broker failures —
    the paper record must reflect the decision even if the sell errors.
    """
    if health.action != "exit":
        return False
    exit_price = float(pos.get("mark_price") or pos.get("entry_price") or 0.0)
    equity_ledger.close_position(
        position_id=pos["id"],
        exit_price=exit_price,
        exit_reason="thesis_invalidated",
        closed_at=now,
    )
    if alpaca_executor is not None and pos.get("execution_provider") == "alpaca_paper":
        try:
            order = alpaca_executor.sell(pos["ticker"], float(pos["shares"]))
            print(f"  ALPACA SELL [{pos['ticker']}] (thesis exit) order_id={order.id} status={order.status}")
        except Exception as exc:
            print(f"  ALPACA SELL FAILED [{pos['ticker']}] (thesis exit): {exc}")
    fp_tracker.record_exit_for_open_trade(
        ticker=pos["ticker"],
        sleeve=pos.get("sleeve"),
        strategy=pos.get("strategy"),
        exit_price=exit_price,
        is_gap_stop=False,
    )
    return True


def _pyramid_addon_candidates(open_positions: list[dict]) -> list[dict]:
    """Open swing positions eligible for a confirm-then-size add-on tranche."""
    out = []
    for pos in open_positions:
        if pos.get("sleeve") != "swing" or pos.get("status") != "open":
            continue
        try:
            analysis = json.loads(pos.get("analysis_json") or "{}")
        except ValueError:
            continue
        tranche = int(analysis.get("tranche") or 0)
        if tranche < 1 or tranche >= 3:
            continue  # not a pyramid position, or already full
        mark = pos.get("mark_price")
        entry = pos.get("entry_price")
        if mark is None or entry is None or mark <= entry:
            continue  # only add to winners — that is the whole point
        out.append(pos)
    return out


def _map_regime_to_vol_label(macro_regime: str) -> str:
    """Map MacroRegimeGate output (crisis/risk_off/neutral/risk_on) to vol labels.

    crisis or risk_off → high_vol
    neutral or risk_on → low_vol
    """
    if macro_regime in ("crisis", "risk_off"):
        return "high_vol"
    return "low_vol"


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
    run_cutoff_utc = datetime.now(tz=timezone.utc).isoformat()
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
        # First: returns few items but high signal, and the composite stops
        # once `limit` is filled. No-op if TRUTH_SOCIAL_API_KEY absent.
        TruthSocialNewsProvider(),
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
        trail_r=settings.equity_trail_r,
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

        # --- Concentration rebalance (sell side of the per-name cap) ---
        # The risk kernel caps concentration at entry only; nothing reduces a
        # name that drifted past the limit through price moves or DCA adds.
        # Off by default — see equity_rebalance_enabled.
        if getattr(settings, "equity_rebalance_enabled", False):
            with _stage(stats, "rebalance"):
                if alpaca_executor is None:
                    print("  [REBALANCE] no broker executor; skipping")
                else:
                    try:
                        broker_positions = alpaca_executor.list_positions()
                        account = alpaca_executor.get_account()
                        trims = compute_trims(
                            [
                                {
                                    "ticker": p.symbol,
                                    "market_value": p.market_value,
                                    "shares": p.qty,
                                }
                                for p in broker_positions
                            ],
                            equity=account.portfolio_value,
                            max_name_pct=settings.equity_max_name_pct,
                            band=settings.equity_rebalance_band,
                        )
                        if not trims:
                            print(
                                f"  [REBALANCE] all names within "
                                f"{settings.equity_max_name_pct:.0%} cap"
                            )
                        for trim in trims:
                            print(f"  [REBALANCE] {trim.evidence}")
                            if dry_run:
                                print(f"  [DRY RUN] would sell {trim.shares:.4f} {trim.ticker}")
                                continue
                            try:
                                order = alpaca_executor.sell(trim.ticker, trim.shares)
                                print(f"  [TRIMMED] {trim.ticker} order={order.id} status={order.status}")
                            except Exception as exc:
                                print(f"  [TRIM FAILED] {trim.ticker}: {type(exc).__name__}: {exc}")
                    except Exception as exc:
                        print(f"  [REBALANCE] skipped: {type(exc).__name__}: {exc}")

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
                by_id = {p["id"]: p for p in open_swing}
                health_checker = ThesisHealthChecker()
                for health in health_checker.check_all(open_swing, news):
                    print(f"  [HEALTH] {health.ticker}: {health.status} -> {health.action} | {health.reason}")
                    pos = by_id.get(health.position_id)
                    if pos is None:
                        continue
                    executed = _execute_thesis_exit(
                        health, pos, equity_ledger, fp_tracker,
                        alpaca_executor, datetime.now(tz=timezone.utc),
                    )
                    if executed:
                        print(f"  [THESIS EXIT] {health.ticker}: closed — {health.reason}")
                        if alerts is not None and _telegram_allows("exit"):
                            await _send_alert(f"Thesis exit EXECUTED: {health.ticker} — {health.reason}")

        # --- Scale-in: add tranches to confirmed winners (dark ship) ---
        if settings.equity_pyramid_enabled and not mark_only:
            with _stage(stats, "scale_in"):
                for pos in _pyramid_addon_candidates(equity_ledger.open_positions()):
                    analysis = json.loads(pos["analysis_json"])
                    add_shares = float(analysis["planned_shares"]) / 3.0
                    next_tranche = int(analysis["tranche"]) + 1
                    if alpaca_executor is not None and pos.get("execution_provider") == "alpaca_paper":
                        # buy() needs a Recommendation; reconstruct the minimum it reads
                        # (instrument.ticker + entry). ponytail: ledger keeps probe shares,
                        # reconcile round-trips the true broker qty.
                        add_rec = Recommendation(
                            instrument=Instrument(pos["ticker"], pos["ticker"], "", CapTier.LARGE),
                            sleeve=Sleeve.SWING, side="buy",
                            entry=float(pos.get("mark_price") or pos["entry_price"]),
                            stop_loss=pos.get("stop_loss"), take_profit=pos.get("take_profit"),
                            size_pct=0.0, confidence=float(pos.get("confidence") or 0.5),
                            catalyst="pyramid_add", thesis=pos.get("thesis", ""), horizon="",
                        )
                        try:
                            order = alpaca_executor.buy(add_rec, add_shares, max_notional=settings.max_order_usd)
                            print(f"  [SCALE IN] {pos['ticker']} tranche {next_tranche}: +{add_shares:.4f} sh order={order.id}")
                        except Exception as exc:
                            print(f"  [SCALE IN FAILED] {pos['ticker']}: {exc}")
                            continue
                    equity_ledger.update_analysis_field(pos["id"], "tranche", next_tranche)

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

            # A degraded price feed silently disables the technical gate, so
            # retry once before trusting a collapsed coverage number.
            if not _tech_coverage_ok(coverage.screened, coverage.total):
                print(
                    f"  [TECH COVERAGE] only {coverage.screened}/{coverage.total} screened; "
                    "retrying price feed once before gating"
                )
                time.sleep(_TECH_COVERAGE_RETRY_SLEEP_S)
                rs_evidence = rs_scanner.scan(swing_universe)
                coverage = rs_scanner.coverage

            print("\n=== Relative-strength screening coverage ===")
            print("scope=curated_swing_universe (not entire stock market)")
            print(f"total_universe={coverage.total}")
            print(f"successfully_screened={coverage.screened}")
            print(f"skipped_failed={len(coverage.failed)}")
            for ticker, reason in coverage.failed.items():
                print(f"  ticker={ticker} reason={reason}")
            hard_gate = getattr(settings, "equity_hard_tech_gate", True)

            # Fail closed: if the feed collapsed, the gate cannot evaluate
            # anything, so it must not approve anything either. Core DCA and
            # mark-to-market are unaffected.
            if hard_gate and not _tech_coverage_ok(coverage.screened, coverage.total):
                print(
                    f"  [TECH COVERAGE] DEGRADED — {coverage.screened}/{coverage.total} "
                    f"below {_MIN_TECH_COVERAGE:.0%}; skipping all swing entries this run"
                )
                swing_candidates = []

            swing_candidates = _apply_tech_gate(
                swing_candidates, rs_evidence, coverage, hard_gate
            )

        # --- Supply-chain-lag / bottleneck screen ---
        # Placed AFTER relative_strength_screen deliberately: these are laggards
        # by definition, so they must bypass the momentum tech gate above.
        with _stage(stats, "supply_chain_lag_screen"):
            try:
                lag_screen = SupplyChainLagScreen(price_feed)
                lag_candidates = lag_screen.scan()
            except Exception as exc:
                print(f"  [SCREEN FAILED] supply_chain_lag_screen error={exc}")
                record_provider_failure()
                lag_candidates = []
            lag_events = [_lag_candidate_to_event(c, swing_universe) for c in lag_candidates]
            for c, event in zip(lag_candidates, lag_events):
                print(
                    f"  [LAG] {c.ticker} ({c.strategy}): {event.evidence} "
                    f"(urgency={event.urgency:.2f})"
                )
            swing_candidates = swing_candidates + lag_events

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
                # Pass the configured lookback: the providers fetch
                # politician_lookback_days but the screen defaulted to 30, so
                # disclosures between the two windows were fetched and dropped.
                pol_candidates = PoliticianScreen(
                    pol_provider, lookback_days=settings.politician_lookback_days
                ).scan(swing_universe)
                for c in pol_candidates:
                    print(f"  [POL] {c.instrument.ticker}: {c.evidence} (urgency={c.urgency:.2f})")

                # This screen runs after relative_strength_screen, so its
                # candidates used to reach the analyst without ever meeting the
                # technical gate — the same name could be dropped as
                # do_not_chase on the filings path and re-enter ungated here.
                # A disclosure is a reason to look, not a reason to chase.
                if hard_gate and not _tech_coverage_ok(coverage.screened, coverage.total):
                    print("  [TECH COVERAGE] DEGRADED — skipping politician entries this run")
                    pol_candidates = []
                else:
                    pol_candidates = _apply_tech_gate(
                        pol_candidates, rs_evidence, coverage, hard_gate, label="POL TECH GATE"
                    )
                swing_candidates = swing_candidates + pol_candidates

                # --- Point-in-time check for politician disclosures (warning-only) ---
                if pol_candidates:
                    try:
                        fetch = pol_provider.fetch()
                        if fetch.trades:
                            most_recent_filed = max(
                                (t.date_filed for t in fetch.trades if t.date_filed),
                                default=None
                            )
                            if most_recent_filed:
                                most_recent_utc = most_recent_filed.isoformat() + "T00:00:00Z"
                                sources_list = [{"name": "politician_disclosure", "as_of_utc": most_recent_utc}]
                                assert_point_in_time(run_cutoff_utc, sources_list)
                    except LookAheadError as e:
                        print(f"  WARNING [PIT] {e}")

        # --- Core screen ---
        with _stage(stats, "core_screen"):
            fundamentals_provider = _FundamentalsFailureAdapter(
                YFinanceFundamentals(),
                failure_callback=record_provider_failure,
                timeout=settings.equity_provider_timeout_seconds,
            )
            quality_screen = QualityScreen(fundamentals_provider)
            core_scan_universe = _dedup_union(core_universe, swing_universe)
            core_candidates = quality_screen.scan(core_scan_universe)

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

        # --- Signal statistics (regime-conditional win rates) ---
        vol_regime = _map_regime_to_vol_label(regime_snap.regime)
        with _stage(stats, "signal_stats"):
            try:
                update_signal_stats(equity_ledger, regime=vol_regime, window_days=30)
                print(f"  Updated signal stats for regime={vol_regime}")
            except Exception as exc:
                print(f"  [SIGNAL_STATS] update failed: {exc}")

        def signal_stats_getter(candidate):
            """Returns historical win-rate line for this candidate's signal class."""
            try:
                signal_class = candidate.event_type.value
                line = signal_stats_line(equity_ledger, signal_class, vol_regime, min_trades=10)
                return line or ""
            except Exception:
                return ""

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
                signal_stats_getter=signal_stats_getter,
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
        def _win_stats_lookup(confidence: float) -> tuple[int, float]:
            from equities.analysis.attribution import _conf_band, confidence_band_stats
            bucket = confidence_band_stats(str(settings.equity_ledger_path)).get(
                _conf_band(confidence)
            )
            if bucket is None:
                return (0, 0.0)
            return (bucket.n, bucket.win_rate)

        correlation_checker = (
            CorrelationChecker(
                price_feed,
                lookback_days=settings.equity_correlation_lookback_days,
            )
            if settings.equity_correlation_enabled
            else None
        )
        news_guard = NewsGuard(
            enabled=settings.equity_news_blackout_enabled,
            before_hours=settings.equity_news_blackout_before_h,
            after_hours=settings.equity_news_blackout_after_h,
            failure_callback=record_provider_failure,
        )
        kernel = RiskKernel(
            capital=settings.bankroll_usd,
            risk_pct=settings.equity_risk_pct,
            max_positions=settings.equity_max_positions,
            max_name_pct=settings.equity_max_name_pct,
            max_sector_pct=settings.equity_max_sector_pct,
            max_gross_pct=settings.equity_max_gross_pct,
            daily_loss_limit_pct=settings.equity_daily_loss_limit_pct,
            drawdown_limit_pct=settings.equity_drawdown_limit_pct,
            min_rr=settings.equity_min_rr,
            kelly_fraction=settings.kelly_fraction,
            kelly_min_trades=settings.equity_kelly_min_trades,
            win_stats_lookup=_win_stats_lookup,
            state_path=Path("data/kernel_state.json"),
            max_pairwise_corr=settings.equity_max_pairwise_corr,
            max_portfolio_corr=settings.equity_max_portfolio_corr,
            correlation_checker=correlation_checker,
        )
        open_positions = equity_ledger.open_positions()
        sector_lookup: dict[str, str] = {}

        def sector_for(ticker: str) -> str:
            if ticker in sector_lookup:
                return sector_lookup[ticker]
            try:
                sector_lookup[ticker] = fundamentals_provider.fetch(ticker).sector
            except RuntimeError:
                raise
            except Exception as exc:
                # Sector is only used for the concentration cap — a flaky/timed-out
                # fundamentals fetch must not abort the whole run. Default to "".
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

        # Gross exposure is the fuse most likely to silently bind; print it every
        # run so "why did nothing trade today" is answerable from the log alone.
        gross_open = sum(
            p.get("shares", 0) * (p.get("mark_price") or p.get("entry_price", 0))
            for p in open_positions
        )
        print(
            f"\n=== Exposure: gross=${gross_open:,.0f} equity=${current_equity:,.0f} "
            f"ratio={gross_open / current_equity if current_equity else 0:.1%} "
            f"cap={settings.equity_max_gross_pct:.0%} "
            f"headroom=${settings.equity_max_gross_pct * current_equity - gross_open:,.0f} ==="
        )

        with _stage(stats, "risk_and_execution"):
            print(f"\n=== Swing recommendations: {len(swing_recommendations)} ===")
            print(f"=== Core DCA recommendations: {len(core_recommendations)} ===")
            for rec in all_recommendations:
                stats.check_runtime()
                # Apply sizing verdict from challenger debate
                rec, sizing_decision = _apply_sizing_verdict(rec)
                if sizing_decision == "skip":
                    reason = f"sizing_debate: {rec.size_rationale}"
                    print(f"  REJECTED [{rec.instrument.ticker}] ({rec.sleeve.value}): {reason}")
                    artifact_store.append(risk_decision_artifact(
                        rec, decision="rejected", rejection_reason=reason, stage="sizing_debate",
                        shares=0,
                        risk_metrics={"open_positions": len(open_positions), "current_equity": current_equity},
                        data_cutoff_utc=run_cutoff_utc,
                    ))
                    continue

                if sizing_decision == "proceed" and rec.size_verdict == "half":
                    print(f"  [SIZED DOWN] [{rec.instrument.ticker}] halved to {rec.size_pct:.2%}")

                # --- News/macro-event blackout (FOMC/CPI/NFP) — new entries only ---
                news_verdict = news_guard.evaluate(
                    rec.instrument.ticker, datetime.fromisoformat(run_cutoff_utc)
                )
                if news_verdict["decision"] == "block":
                    reason = f"news_blackout: {news_verdict['reason']} (next_event={news_verdict['next_event']}, minutes_until={news_verdict['minutes_until']})"
                    print(f"  REJECTED [{rec.instrument.ticker}] ({rec.sleeve.value}): {reason}")
                    artifact_store.append(risk_decision_artifact(
                        rec, decision="rejected", rejection_reason=reason, stage="news_guard",
                        shares=0,
                        risk_metrics={"next_event": news_verdict["next_event"], "minutes_until": news_verdict["minutes_until"]},
                        data_cutoff_utc=run_cutoff_utc,
                    ))
                    continue

                sized = kernel.approve(
                    rec,
                    open_positions,
                    today_realized_loss=today_realized_loss,
                    # Drawdown breaker needs mark-to-market equity, NOT deployable_equity
                    # (which nets out capital in open positions and falsely reads as a
                    # huge drawdown the moment the book is invested → permanent halt).
                    current_equity=current_equity,
                    sector_lookup=sector_lookup,
                )
                if not sized.approved:
                    print(f"  REJECTED [{rec.instrument.ticker}] ({rec.sleeve.value}): {sized.rejection_reason}")
                    artifact_store.append(risk_decision_artifact(
                        rec, decision="rejected", rejection_reason=sized.rejection_reason or "risk_kernel_rejected",
                        stage="risk", shares=sized.shares,
                        risk_metrics={"open_positions": len(open_positions), "current_equity": current_equity},
                        data_cutoff_utc=run_cutoff_utc,
                    ))
                    continue

                # Probe-then-pyramid (dark ship): open 1/3, stamp tranche so the
                # scale_in stage can add on confirmation. Replacing `sized` once
                # propagates the probe size to every downstream sized.shares use.
                if settings.equity_pyramid_enabled and rec.sleeve.value == "swing":
                    _full_shares = sized.shares
                    sized = replace(sized, shares=_full_shares / 3.0)
                    rec = replace(rec, analysis={
                        **(rec.analysis or {}),
                        "tranche": 1,
                        "planned_shares": _full_shares,
                    })

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
                        data_cutoff_utc=run_cutoff_utc,
                    ))
                    continue
                if alpaca_executor is not None and _todays_alpaca_order_count(equity_ledger) >= settings.max_daily_order_count:
                    reason = f"max_daily_order_count={settings.max_daily_order_count}_reached"
                    print(f"  REJECTED [{rec.instrument.ticker}] ({rec.sleeve.value}): {reason}")
                    artifact_store.append(risk_decision_artifact(
                        rec, decision="rejected", rejection_reason=reason, stage="daily_cap",
                        shares=sized.shares, notional=order_notional,
                        data_cutoff_utc=run_cutoff_utc,
                    ))
                    continue

                # Idempotency: never stack a second same-day buy of a name already
                # held from a run earlier today (survives share-count drift that
                # defeats the client_order_id guard). DCA adds on later days are fine.
                _today_iso = datetime.now(tz=timezone.utc).date().isoformat()
                if equity_ledger.ticker_active_today(rec.instrument.ticker, _today_iso):
                    reason = "already_opened_today"
                    print(f"  SKIPPED [{rec.instrument.ticker}] ({rec.sleeve.value}): {reason}")
                    artifact_store.append(risk_decision_artifact(
                        rec, decision="rejected", rejection_reason=reason, stage="same_day_guard",
                        shares=sized.shares, notional=order_notional,
                        data_cutoff_utc=run_cutoff_utc,
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
                            data_cutoff_utc=run_cutoff_utc,
                        ))
                        continue
                    local_status = _local_status_for(order.status)
                    if local_status == "rejected":
                        print(f"  ALPACA REJECTED [{rec.instrument.ticker}]: broker_status={order.status}")
                        artifact_store.append(risk_decision_artifact(
                            rec, decision="rejected", rejection_reason=f"broker_status: {order.status}",
                            stage="broker", shares=sized.shares, notional=order_notional,
                            data_cutoff_utc=run_cutoff_utc,
                        ))
                        continue
                    filled_shares = order.filled_qty if order.filled_qty > 0 else sized.shares
                    ledger_entry_price = order.filled_avg_price if order.filled_avg_price is not None else rec.entry
                    signal_class = (rec.analysis or {}).get("signal_class", "")
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
                        signal_class=signal_class,
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
                    signal_class = (rec.analysis or {}).get("signal_class", "")
                    position_id = equity_ledger.open_position(
                        rec,
                        sized.shares,
                        rec.entry,
                        datetime.now(tz=timezone.utc),
                        mode="paper",
                        strategy="equity_analyst",
                        sector=sector_lookup.get(rec.instrument.ticker, ""),
                        signal_class=signal_class,
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
                # Shadow sizing: compute vol-target shares for A/B analysis (never affects execution)
                sizing_dict = {"kelly_shares": fill.shares}
                try:
                    closes = prices.closes(rec.instrument.ticker)
                    if closes is not None:
                        vol_pct = vol_20d_ann_pct(closes)
                        if vol_pct is not None:
                            vt_shares = vol_target_shares(
                                entry=rec.entry,
                                vol_20d_ann_pct=vol_pct,
                                capital=deployable_equity,
                            )
                            if vt_shares is not None:
                                sizing_dict["voltarget_shares"] = vt_shares
                except Exception:
                    pass  # Shadow computation can never break execution
                artifact_store.append(risk_decision_artifact(
                    rec, decision="approved", stage="risk",
                    shares=fill.shares, notional=fill.shares * fill.entry_price,
                    data_cutoff_utc=run_cutoff_utc,
                    sizing=sizing_dict,
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

    # Refresh the frontend's static snapshots so the website isn't stale.
    # Only when running from the repo (skips silently for the pip-installed CLI,
    # which has no frontend/ dir). ponytail: regen only; deploy stays manual.
    regen = Path("scripts/generate_frontend_data.py")
    if not args.dry_run and regen.is_file() and Path("frontend/public").is_dir():
        try:
            subprocess.run([sys.executable, str(regen)], check=True)
        except Exception as exc:  # never fail the pipeline on a frontend-export hiccup
            print(f"WARN: frontend data regen failed: {exc}")


if __name__ == "__main__":
    main()
