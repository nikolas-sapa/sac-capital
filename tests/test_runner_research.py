from runner_research import opportunity_score


def test_opportunity_score_rewards_fresh_lag_and_bottleneck():
    score = opportunity_score(
        lag_1y=-20.0,
        lag_3mo=30.0,
        lag_1mo=20.0,
        bottleneck=0.5,
    )

    assert score == 0.085


def test_opportunity_score_ignores_negative_lag():
    score = opportunity_score(
        lag_1y=-20.0,
        lag_3mo=-30.0,
        lag_1mo=-10.0,
        bottleneck=0.8,
    )

    assert score == 0.0
