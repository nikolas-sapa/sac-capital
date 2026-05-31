# Polymarket Multi-Strategy Bot — Master Spec

> **Status:** FINALIZED after grill-me stress test.

## Grill-Me Resolved Decisions

1. **LLM bot edge thesis = thin/illiquid markets.** Claude is not assumed smarter than experts; the edge is the *absence of sharp competition* in low-volume markets with stale prices. This is a HYPOTHESIS, not a belief.
2. **Hard kill-gate for the LLM bot:** the resolved-market Brier backtest (Plan 02 Task 6) is the truth oracle. If Claude shows no calibration edge on ≥50 historical resolved markets, the LLM bot is killed before it paper-trades. No sunk-cost continuation.
3. **Resolution loop is mandatory infra:** a nightly gamma-api poller marks open paper positions win/loss and updates ledger PnL. Paper trading is theater without it (added: Foundation Task 13).
4. **Deploy target:** Mac + launchd for the paper phase; cheap Linux VPS + systemd only when a strategy goes live. **Hugging Face free Spaces are explicitly rejected** — ephemeral storage wipes the ledger on restart; UptimeRobot pinging keeps a Space awake but cannot give persistent disk.
5. **Go-live bar (per strategy):** ≥100 resolved paper trades AND positive ROI net of simulated fees/slippage AND (for probability bots) Brier score beating the market's own implied probability. 30 trades is noise.
6. **LLM cost control (engineering call):** two-stage — a cheap-model (Haiku) pass filters the candidate set, Sonnet does the final probability estimate only on survivors; hard cap on candidates per cycle + a daily USD budget guard that halts LLM calls when exceeded.

## Goal

Build a Python monorepo that runs three independent Polymarket trading strategies (LLM probability, weather, crypto Up/Down repricing) in **paper-trade mode**, with a capital-allocator orchestrator on top. Prove edge on simulated fills before any real money touches the system.

## Hard Constraints (decided)

- **Language:** Python 3.12 monorepo, single venv, `uv` for dependency management.
- **Money:** Paper trading only. No wallet, no USDC, no live orders until a strategy proves positive ROI over ≥30 simulated trades. Going live is a separate, gated decision.
- **Target bankroll (post-proof):** €750–1,000. Free data feeds only (open-meteo, raw CLOB websocket, public price APIs). Paid feeds (ECMWF ensemble, Visual Crossing) deferred until a strategy is live and profitable.
- **No real-money execution code ships in the first milestone.** The live executor is stubbed/guarded behind an explicit `LIVE=true` flag that does not exist yet.

## Why This Architecture

This mirrors a multi-strategy hedge fund: uncorrelated sub-strategies feeding a capital allocator. The orchestrator is NOT built first — it emerges once two strategies are live in paper mode and start competing for simulated capital.

Build order (each milestone produces working, testable software on its own):

1. **Foundation** — shared platform every bot needs. Nothing trades until this exists.
2. **LLM Probability Bot** — fastest to ship, teaches the CLOB + market data layer.
3. **Weather Bot** — non-correlated domain edge, most documented playbook.
4. **Crypto Up/Down Bot** — hardest, needs speed; build last.
5. **Orchestrator** — capital router; emerges naturally with 2+ live strategies.
6. **Self-Improvement Harness + Obsidian** — bounded, evidence-gated learning loop + human-readable audit trail. The Obsidian *writer* can be built alongside Foundation (journaling is useful immediately); the *learning mechanisms* come after strategies produce resolved trades. See `06-self-improvement-harness.md`.

> **The harness is NOT magic self-rewriting.** It is four bounded feedback loops (LLM calibration correction, per-station weather bias, walk-forward threshold re-tuning, capital re-weighting), each gated by held-out validation, min-sample thresholds, capped step sizes, version history, and auto-rollback. Structural changes require human approval via an Obsidian checkbox + Telegram. This is the antidote to the "bot reprograms itself overnight" hype — improvement must be *earned with out-of-sample evidence*.

## Monorepo Structure

```
polymarket-bot/
├── pyproject.toml              # uv-managed, single venv
├── .env.example                # API keys, no secrets committed
├── docs/plans/                 # these plans
├── core/                       # SHARED PLATFORM (Foundation milestone)
│   ├── clob/
│   │   ├── client.py           # raw websocket client to clob.polymarket.com
│   │   └── rest.py             # gamma-api REST for market metadata
│   ├── markets.py              # Market, OrderBook, Outcome domain types
│   ├── sizing/
│   │   └── kelly.py            # Kelly + fractional-Kelly position sizing
│   ├── probability/
│   │   └── bayes.py            # Bayesian shock-update engine
│   ├── execution/
│   │   ├── base.py             # Executor protocol
│   │   └── paper.py            # PaperExecutor — simulated fills, CSV ledger
│   ├── alerts/
│   │   └── telegram.py         # aiogram alert sink
│   ├── strategy.py             # Strategy protocol all bots implement
│   ├── config.py               # pydantic-settings config loader
│   └── ledger.py               # trade/PnL recording (CSV + sqlite)
├── strategies/
│   ├── llm_probability/
│   ├── weather/
│   └── crypto_updown/
├── orchestrator/
│   └── allocator.py            # portfolio-level capital router
├── runner.py                   # entrypoint: loads enabled strategies, runs loop
└── tests/                      # pytest, mirrors source tree
```

## Shared Contracts (locked across all plans)

These types are defined ONCE in Foundation and reused. Every later plan depends on these exact signatures.

```python
# core/markets.py
@dataclass(frozen=True)
class Outcome:
    token_id: str          # CLOB ERC1155 token id
    label: str             # "Yes" / "No" / bin label
    best_bid: float        # 0.0–1.0
    best_ask: float        # 0.0–1.0

@dataclass(frozen=True)
class Market:
    condition_id: str      # Polymarket condition id
    question: str
    outcomes: list[Outcome]
    end_date: datetime     # resolution time (UTC)
    closed: bool

# core/strategy.py
@dataclass(frozen=True)
class Signal:
    market: Market
    token_id: str          # which outcome to buy
    fair_prob: float       # strategy's estimated true probability (0–1)
    price: float           # current ask we'd pay
    confidence: float      # 0–1, drives orchestrator weighting
    reason: str            # human-readable why

class Strategy(Protocol):
    name: str
    def scan(self, markets: list[Market]) -> list[Signal]: ...

# core/sizing/kelly.py
def kelly_fraction(p: float, price: float, frac: float = 0.5) -> float:
    """Fractional Kelly. p=true prob, price=ask (0-1). Returns fraction of bankroll."""

# core/execution/base.py
class Executor(Protocol):
    def place(self, signal: Signal, stake: float) -> "Fill": ...

@dataclass(frozen=True)
class Fill:
    signal: Signal
    stake: float
    shares: float
    avg_price: float
    timestamp: datetime
    mode: str              # "paper" | "live"
```

## Universal Risk Rules (enforced by orchestrator + every strategy)

- **Fractional Kelly default = 0.5** (half-Kelly), never full Kelly.
- **Hard cap: no single position > 2% of bankroll**, regardless of Kelly output.
- **Skip, don't force:** if a strategy can't find a clean edge, it returns no signal. Better not to trade.
- **Per-strategy daily loss limit:** halt a strategy for the day if its simulated PnL drops below a configured threshold.
- **Total exposure cap:** orchestrator never allocates >X% of bankroll across all open positions simultaneously.

## Edge Sources (the actual alpha, per credible research)

1. **Speed** — raw CLOB websocket, never REST polling or wrapped clients in the hot path.
2. **Probability calibration** — LLM returns calibrated prob vs. market price (the LLM bot's core).
3. **Kelly sizing** — the compounding multiplier; flat betting is why most lose.
4. **Bayesian shock update** — re-price instantly on >8%/60s moves with no orderbook cause.
5. **Reliability** — systemd auto-restart + Telegram alerts; uptime is free alpha.

## Definition of Done (Foundation)

- CLOB websocket connects, streams a live orderbook for a real market, parses into `OrderBook`.
- `kelly_fraction` and `bayes` engines unit-tested.
- `PaperExecutor` records simulated fills to a CSV ledger with realistic fee/slippage assumptions.
- A trivial dummy strategy runs end-to-end through `runner.py` and logs a paper fill.
- Telegram alert fires on a simulated fill.

## Definition of Done (each bot)

- Implements the `Strategy` protocol.
- Has a backtest/replay validation (where data allows) before paper.
- Runs ≥100 RESOLVED paper trades; tearsheet shows ROI net of costs, win rate, Brier score, max drawdown.
- Positive ROI net of simulated fees/slippage, and (probability bots) Brier beats market-implied prob.
- Only then is it a candidate for the live-gating decision (a separate, deliberate choice — not automatic).
