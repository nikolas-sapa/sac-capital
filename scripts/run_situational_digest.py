"""Launchd entrypoint for the nightly situational-awareness digest."""
from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import load_config
from equities.data.prices import YFinancePriceFeed
from equities.eval.replay import ArtifactReplayEvaluator
from equities.eval.situational_digest import SituationalDigestBuilder, send_digest
from equities.ledger_equity import EquityLedger
from equities.research.store import ResearchArtifactStore

VALIDATION_LOOKBACK_DAYS = 90


def main() -> None:
    settings = load_config()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        print("ERROR: telegram_bot_token and telegram_chat_id must be configured")
        sys.exit(1)

    data_dir = Path("data")

    equity_ledger = EquityLedger(data_dir / "equity.db")
    try:
        open_positions = equity_ledger.open_positions()
    finally:
        equity_ledger.close()

    store = ResearchArtifactStore(data_dir / "research_artifacts.jsonl")
    evaluator = ArtifactReplayEvaluator(YFinancePriceFeed())
    replay_report = evaluator.evaluate(
        store.read_all(),
        validation_start=date.today() - timedelta(days=VALIDATION_LOOKBACK_DAYS),
    )

    builder = SituationalDigestBuilder()
    asyncio.run(
        send_digest(
            builder,
            open_positions=open_positions,
            replay_report=replay_report,
            telegram_token=settings.telegram_bot_token,
            telegram_chat_id=settings.telegram_chat_id,
        )
    )
    print("situational digest sent")


if __name__ == "__main__":
    main()
