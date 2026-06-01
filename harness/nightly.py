from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from core.ledger import Ledger
    from harness.obsidian import ObsidianVault
    from harness.params import ParamStore
    from orchestrator.performance import RollingStats


class Learner(Protocol):
    """A learning mechanism that may propose a parameter change."""

    def run(
        self,
        stats: "dict[str, RollingStats]",
        store: "ParamStore",
        vault: "ObsidianVault",
    ) -> dict[str, Any] | None:
        """Return a change dict or None.

        Change dict keys: strategy, key, value, reason, evidence, type ("auto"|"approval")
        """
        ...


def run_nightly(
    ledger: "Ledger",
    store: "ParamStore",
    vault: "ObsidianVault",
    learners: list[Learner],
) -> dict[str, Any]:
    """Orchestrate the nightly self-improvement consolidation.

    1. Recompute per-strategy rolling stats
    2. Run each learner (may propose auto or approval changes)
    3. Apply auto changes via store + changelog
    4. Queue approval changes as Obsidian proposals
    5. Apply any human-approved proposals from previous nights
    6. Write the daily Obsidian log + update index
    """
    from harness.approval import apply_approved
    from orchestrator.performance import StrategyStats

    today = date.today()
    stats_engine = StrategyStats(ledger)

    rows = ledger._con.execute(
        "SELECT DISTINCT strategy FROM fills WHERE strategy != ''"
    ).fetchall()
    strategy_names = [r["strategy"] for r in rows]
    stats = {name: stats_engine.rolling(name, window=100) for name in strategy_names}

    log_entries: list[str] = []
    auto_applied: list[dict] = []
    approval_queued: list[str] = []

    for learner in learners:
        result = learner.run(stats, store, vault)
        if result is None:
            continue

        change_type = result.get("type", "approval")

        if change_type == "auto":
            store.set(
                result["strategy"],
                result["key"],
                result["value"],
                reason=result.get("reason", ""),
                evidence=result.get("evidence", ""),
            )
            vault.append_changelog(
                f"[{today}] AUTO {result['strategy']}.{result['key']}"
                f" = {result['value']} — {result.get('reason', '')}"
            )
            auto_applied.append(result)
            log_entries.append(
                f"- AUTO applied: {result['strategy']}.{result['key']} = {result['value']}"
            )
        else:
            slug = f"{result['strategy']}-{result['key']}"
            body = "\n".join([
                f"strategy: {result['strategy']}",
                f"key: {result['key']}",
                f"value: {result['value']}",
                f"reason: {result.get('reason', '')}",
                "",
                f"## Evidence\n{result.get('evidence', '')}",
            ])
            vault.write_proposal(slug, body)
            approval_queued.append(slug)
            log_entries.append(f"- APPROVAL queued: {slug}")

    newly_applied = apply_approved(vault, store)
    for slug in newly_applied:
        log_entries.append(f"- APPROVED applied: {slug}")

    stats_summary = "\n".join(
        f"  {name}: n={s.n_resolved} win_rate={s.win_rate:.1%} roi={s.roi:+.2%}"
        for name, s in stats.items()
    ) or "  (no resolved trades yet)"

    daily_content = (
        f"# Nightly Consolidation — {today}\n\n"
        f"## Strategy Performance\n{stats_summary}\n\n"
        f"## Changes\n"
        + ("  (none)\n" if not log_entries else "\n".join(log_entries) + "\n")
        + f"\n## Open Positions\n  count: {len(ledger.open_positions())}\n"
    )
    vault.write_daily(today, daily_content)

    vault.update_index({
        "date": today.isoformat(),
        "strategies": len(strategy_names),
        "total_pnl": f"{ledger.pnl():.2f}",
        "open_positions": len(ledger.open_positions()),
        "auto_applied_today": len(auto_applied),
        "approvals_pending": len(approval_queued),
    })

    return {
        "auto_applied": auto_applied,
        "approval_queued": approval_queued,
        "approved_applied": newly_applied,
        "stats": stats,
    }
