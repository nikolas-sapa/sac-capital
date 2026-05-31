from dataclasses import dataclass
from datetime import datetime


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

    def outcome_by_token(self, token_id: str) -> Outcome:
        """Return the outcome with the given token_id; raise KeyError if none match."""
        for outcome in self.outcomes:
            if outcome.token_id == token_id:
                return outcome
        raise KeyError(token_id)
