from core.assets.instrument import CapTier, Instrument
from equities.research.artifacts import EquityResearchArtifact, risk_decision_artifact
from equities.strategy import Recommendation, Sleeve


def _rec() -> Recommendation:
    inst = Instrument(ticker="ACME", name="Acme", exchange="NASDAQ", cap_tier=CapTier.SMALL)
    return Recommendation(
        instrument=inst, sleeve=Sleeve.SWING, side="buy",
        entry=10.0, stop_loss=9.0, take_profit=13.0,
        size_pct=0.03, confidence=0.6, catalyst="earnings beat",
        thesis="under-covered, gapped on beat", horizon="1-2 weeks",
    )


def test_rejection_artifact_captures_reason_and_stage():
    art = risk_decision_artifact(
        _rec(),
        decision="rejected",
        rejection_reason="max_concurrent_positions_reached",
        stage="risk",
        risk_metrics={"open_positions": 4, "max_positions": 4},
    )
    assert isinstance(art, EquityResearchArtifact)
    assert art.decision == "rejected"
    assert art.ticker == "ACME"
    assert art.rejection_reason == "max_concurrent_positions_reached"
    assert art.output_json["stage"] == "risk"
    assert art.output_json["risk_metrics"]["open_positions"] == 4
    assert art.confidence == 0.6
    # thesis (why) is preserved even when the trade is skipped
    assert art.output_json["thesis"] == "under-covered, gapped on beat"


def test_approved_artifact_records_shares_and_notional():
    art = risk_decision_artifact(
        _rec(), decision="approved", stage="risk", shares=5.0, notional=50.0,
    )
    assert art.decision == "approved"
    assert art.rejection_reason == ""
    assert art.output_json["shares"] == 5.0
    assert art.output_json["notional"] == 50.0


def test_artifact_id_is_stable_and_distinguishes_decisions():
    a = risk_decision_artifact(_rec(), decision="rejected", rejection_reason="x", stage="risk")
    b = risk_decision_artifact(_rec(), decision="rejected", rejection_reason="x", stage="risk")
    c = risk_decision_artifact(_rec(), decision="approved", stage="risk", shares=5.0)
    assert a.artifact_id == b.artifact_id
    assert a.artifact_id != c.artifact_id
