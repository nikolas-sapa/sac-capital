from __future__ import annotations

from core.markets import Market

SYSTEM_PROMPT = """You are a calibrated probability estimator for prediction markets.
Your estimates will be evaluated by Brier score — do NOT anchor to 0.5 or hedge with
near-50 estimates unless the evidence genuinely supports it. Overconfident AND
underconfident estimates both hurt your score.

Rules:
- Respond with ONLY valid JSON: {"probability": <float 0-1>, "confidence": <float 0-1>, "reasoning": "<string>"}
- probability = your true estimate that the YES outcome resolves
- confidence = how certain you are in that estimate (0=no idea, 1=near-certain)
- reasoning = 1-3 sentences citing specific evidence; do NOT write "I think" or "it seems"
- Never return probability outside [0.01, 0.99]
"""


def build_prompt(market: Market, resolution_text: str) -> str:
    """Build the user-turn prompt for a single Polymarket market."""
    outcomes_str = "\n".join(
        f"  {o.label}: bid={o.best_bid:.2f}, ask={o.best_ask:.2f}"
        for o in market.outcomes
    )
    yes_outcomes = [o for o in market.outcomes if o.label.lower() == "yes"]
    yes_ask = yes_outcomes[0].best_ask if yes_outcomes else "N/A"

    return (
        f"QUESTION: {market.question}\n\n"
        f"RESOLUTION CRITERIA: {resolution_text}\n\n"
        f"CURRENT MARKET PRICES:\n{outcomes_str}\n\n"
        f"Current YES ask (price to buy YES): {yes_ask}\n\n"
        f"Estimate the TRUE probability that YES resolves. "
        f"Return JSON: {{\"probability\": <float>, \"confidence\": <float>, \"reasoning\": \"<string>\"}}"
    )
