from datetime import datetime, timezone, timedelta

from core.markets import Market, Outcome
from strategies.llm_probability.prompt import build_prompt, SYSTEM_PROMPT


def _market() -> Market:
    return Market(
        condition_id="cond_abc",
        question="Will the Fed cut rates in June 2026?",
        outcomes=[
            Outcome(token_id="yes", label="Yes", best_bid=0.42, best_ask=0.45),
            Outcome(token_id="no",  label="No",  best_bid=0.52, best_ask=0.56),
        ],
        end_date=datetime.now(tz=timezone.utc) + timedelta(days=10),
        closed=False,
    )


def test_prompt_contains_question():
    p = build_prompt(_market(), resolution_text="Resolves YES if the FOMC lowers FFR.")
    assert "Will the Fed cut rates" in p


def test_prompt_contains_resolution_criteria():
    p = build_prompt(_market(), resolution_text="Resolves YES if the FOMC lowers FFR.")
    assert "FOMC" in p


def test_prompt_contains_current_yes_ask():
    p = build_prompt(_market(), resolution_text="Resolves YES if the FOMC lowers FFR.")
    assert "0.45" in p


def test_prompt_requests_json_output():
    p = build_prompt(_market(), resolution_text="x")
    assert "probability" in p
    assert "confidence" in p
    assert "reasoning" in p


def test_system_prompt_forbids_hedging():
    assert "0.5" in SYSTEM_PROMPT or "anchor" in SYSTEM_PROMPT
    assert "Brier" in SYSTEM_PROMPT


def test_prompt_includes_all_outcomes():
    p = build_prompt(_market(), resolution_text="x")
    assert "Yes" in p
    assert "No" in p
