from equities.improve.variants import ParameterVariant, generate_variants


def test_baseline_always_included():
    current = {"min_edge": 0.08, "window": 14}
    variants = generate_variants(current, {})
    assert len(variants) == 1
    assert variants[0].name == "baseline"
    assert variants[0].params == current


def test_generates_one_variant_per_candidate():
    current = {"x": 1.0}
    variants = generate_variants(current, {"x": [1.0, 2.0, 3.0]})
    # baseline + 2 challengers (1.0 is current, skipped)
    assert len(variants) == 3
    names = [v.name for v in variants]
    assert "x=2.0" in names
    assert "x=3.0" in names


def test_current_value_not_duplicated():
    current = {"x": 1.0}
    variants = generate_variants(current, {"x": [1.0]})
    assert len(variants) == 1  # only baseline


def test_max_variants_cap():
    current = {"x": 0}
    candidates = list(range(1, 20))  # 19 challengers
    variants = generate_variants(current, {"x": candidates}, max_variants=5)
    assert len(variants) <= 6  # 1 baseline + 5 challengers


def test_params_are_independent_copies():
    current = {"a": 1, "b": 2}
    variants = generate_variants(current, {"a": [1, 3]})
    baseline = variants[0]
    challenger = variants[1]
    assert baseline.params is not challenger.params  # separate dicts
    assert challenger.params["b"] == 2  # other keys preserved
