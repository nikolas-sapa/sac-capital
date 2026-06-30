# Plan 08 — Situational Awareness Additions — SPEC

> **Status:** DESIGNED from a read of Leopold Aschenbrenner's "Situational Awareness" (Jun 2024) + repo audit (2026-06-20). Two independent reviews (mine + a second chat's) converged on the same engineering pattern; repo audit then found **most of the AI-infrastructure thesis machinery already built**. This spec covers only the genuine gaps.
> Next: TDD subagent-driven build, one task per numbered item below.

## What This Is Not

Not a bet on Aschenbrenner's AGI-2027 timeline or geopolitical claims. Those are scenario inputs, not facts the system should trade on. What's durable and worth building: trendline discipline, claim-evidence-verdict structure, tamper-evident provenance, security-before-capability posture.

## Already Built — Do Not Duplicate

Audit found these already implement most of the "add an AI buildout thesis engine" idea from both reviews:

- `equities/research/supply_chain.py` — trunk→leaf graph (NVDA/AMD/AVGO/TSM/etc.) including power/grid names (VRT, ETN, GEV, CEG, PWR) under GOOGL/AMZN trunks. `BottleneckScorer` scores leaf suppliers 0–1.
- `equities/screen/thematic_monitor.py` — theme concentration limits on top of that graph.
- `equities/research/discovery_lag.py` — `DiscoveryLagCalculator` measures trunk-vs-leaf 12m return lag — this *is* the "synthesis edge" detector.
- `equities/research/thesis_miner.py` — `STRUCTURAL_THESES` list already contains, verbatim, "AI inference compute scales 100x by 2027, requiring massive GPU, memory, power, and cooling infrastructure" plus 4 other structural theses (GLP-1, CHIPS Act, grid infra, autonomous defense). `ThesisMiner` LLM-mines 3-level supply chains from each thesis.
- `equities/research/artifacts.py` — `EquityResearchArtifact` already has `SourceRef`, `Citation`, `ExtractionRef`, `prompt_hash`, `stable_hash()`. The claim→evidence schema both reviews proposed adding largely exists.
- `hackathon/verifiability.py` — `Commitment`/`commitment_for_payload` already hashes individual ledger rows and research artifacts deterministically for on-chain anchoring.
- `equities/eval/replay.py` — `ReplayMetrics` already breaks down expectancy by sector and catalyst type, computes alpha/beta vs benchmark, Sortino, max consecutive losses.
- `equities/improve/promoter.py` — kill-gate + cooldown-gated auto-promotion already implements "scalable oversight" for strategy variants.
- `harness/learn/calibration.py` — isotonic calibrator already exists, but it's for Polymarket probability calibration (different domain — see Gap 1 below for why this doesn't cover the macro-thesis case).

## Genuine Gaps (this spec covers these)

### Gap 1: Macro-thesis calibration check

No mechanism scores Aschenbrenner-style **macro timeline predictions** against reality. `harness/learn/calibration.py` calibrates Polymarket probability estimates (different domain, per-market). Nothing checks: did the premise behind `STRUCTURAL_THESES[0]` ("AI inference compute scales 100x by 2027...") track reality from 2024→2026? This is free, already-resolved signal — the essay is 2 years old, several of its numeric predictions (Nvidia datacenter revenue trajectory, AI capex run-rate, power-constraint emergence) are independently checkable now.

**Add:** a one-shot research note + a small scored table comparing named predictions to actuals, used to set a confidence multiplier on `STRUCTURAL_THESES` entries (a thesis whose premise already fully played out / is now consensus gets down-weighted — the edge from `discovery_lag.py` requires the crowd to still be slow).

### Gap 2: Citation→return linkage in replay

`artifacts.py` captures `Citation` objects (source, quote, confidence) per research artifact. `replay.py` computes forward returns per trade but never joins back to *which citations* were behind the thesis. Can't currently answer "which sources predicted returns" — exactly the self-improvement signal flagged in both reviews.

**Add:** extend `ReplayTrade`/`ReplayMetrics` (or a new sibling module) to join `artifact_id` → `EquityResearchArtifact.citations` → forward `pnl_pct`, aggregated by citation `source`.

### Gap 3: Run-level tamper-evident manifest

`verifiability.py` hashes *individual* ledger rows and research artifacts. There's no single hash tying together one full run's config + prompt versions + model IDs + full source set. Per-decision provenance exists; per-run provenance doesn't.

**Add:** a `RunManifest` built once per bot invocation — hashes `{config_snapshot, prompt_versions_used, model_ids, source_ids_fetched}` via the existing `canonical_json`/`stable_hash` pattern, written alongside the run's artifacts.

### Gap 4: Security preflight

Confirmed via grep: no preflight check exists anywhere in the repo. `LIVE=true` is referenced in `equities/risk/kernel.py` docstrings as "not yet implemented" but nothing checks for accidental live-mode flags, missing/placeholder secrets, or `.env` hygiene before a run starts. Aschenbrenner's "treat AGI secrets like nuclear secrets, not SaaS" argument maps directly to "treat broker credentials and the kill-switch flag with the same discipline."

**Add:** a startup preflight script — checks `.env` for required keys present and non-placeholder, confirms `LIVE` flag (if/when implemented) requires explicit opt-in, fails loud (not silent default) on missing secrets.

### Gap 5: Nightly situational-awareness digest

The pieces to build this already exist (`thematic_monitor`, `discovery_lag`, replay's sector/catalyst expectancy breakdowns) but nothing combines them into one digest. Low effort, decent value — mostly glue.

**Add:** a scheduled job that runs `ThematicMonitor.check()`, `DiscoveryLagCalculator.score_all_leaves()` for each `STRUCTURAL_THESES` trunk, and `ReplayReport` sector/catalyst breakdowns, and posts the combined digest via the existing `core.alerts.telegram` pattern.

## Explicitly Deferred (low value-add given current state)

- **More specialist analyst agents** (valuation skeptic, fraud/accounting skeptic) — `equities/analysis/analyst.py` already runs a 3-stage prefilter→bull-thesis→challenger pipeline. Adding more lenses is a prompt-engineering iteration on an existing stage, not new infrastructure. Revisit only if replay data (Gap 2) shows a specific blind spot (e.g. consistently missing accounting red flags).
- **Rebuilding the AI-infrastructure universe/graph** — already covered by `supply_chain.py` + `thesis_miner.py`. Any "add NVDA/TSM/power names" work is a data-update to the existing dict, not a new module.

## Hard Constraints

- Reuse existing patterns: `stable_hash`/`canonical_json` from `hackathon/verifiability.py` for Gap 3, not a new hashing scheme.
- Reuse `core.alerts.telegram` for Gap 5 delivery — do not add a new notification channel.
- No live-trading code introduced by any of these gaps. Gap 4's preflight only *checks for* a `LIVE` flag; it does not implement live execution.
- Gap 1 is a research/data task (no LLM-pipeline change) — a static comparison table + a confidence multiplier field, not a new agent.

## Implementation Order

1. Gap 4 (security preflight) — cheapest, zero dependencies on other gaps, matches "harden before capability increases" principle directly.
2. Gap 1 (macro calibration check) — research-only, informs Gap 5's digest content.
3. Gap 2 (citation→return linkage) — needs existing replay + artifacts data, no new infra.
4. Gap 3 (run manifest) — needs Gap 2's join pattern as a template for how to aggregate IDs.
5. Gap 5 (nightly digest) — last, since it consumes outputs from 1–4.

## File Targets

| Gap | Files |
|---|---|
| 1 | New: `docs/research/situational-awareness-calibration-2026.md`; Modify: `equities/research/thesis_miner.py` (add `confidence_multiplier` field to thesis entries) |
| 2 | Modify: `equities/eval/replay.py`; Test: `tests/equities/test_replay_citations.py` |
| 3 | New: `equities/research/run_manifest.py`; Test: `tests/equities/test_run_manifest.py` |
| 4 | New: `scripts/preflight.py`; Test: `tests/test_preflight.py` |
| 5 | New: `equities/eval/situational_digest.py`; Test: `tests/equities/test_situational_digest.py` |
