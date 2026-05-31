from core.sizing.kelly import kelly_fraction


def test_kelly_positive_edge():
    # p=0.6, price=0.5 -> b=1.0, full kelly=(1*0.6-0.4)/1=0.2; half=0.1
    assert abs(kelly_fraction(0.6, 0.5, frac=0.5) - 0.1) < 1e-9


def test_kelly_no_edge_returns_zero():
    assert kelly_fraction(0.5, 0.5) == 0.0


def test_kelly_negative_edge_clamped_zero():
    assert kelly_fraction(0.4, 0.5) == 0.0


def test_kelly_invalid_price_zero_returns_zero():
    assert kelly_fraction(0.6, 0.0) == 0.0


def test_kelly_invalid_price_one_returns_zero():
    assert kelly_fraction(0.6, 1.0) == 0.0


def test_kelly_p_out_of_range_above_returns_zero():
    assert kelly_fraction(1.1, 0.5) == 0.0


def test_kelly_p_out_of_range_below_returns_zero():
    assert kelly_fraction(-0.1, 0.5) == 0.0
