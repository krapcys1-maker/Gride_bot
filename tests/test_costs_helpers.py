from gridbot.core.costs import compute_breakeven_metrics


def test_breakeven_true_geometric():
    m = compute_breakeven_metrics(
        lower_price=100,
        upper_price=150,
        grid_levels=3,
        grid_type="geometric",
        fee_bps=2,
        spread_bps=2,
        slippage_bps=2,
        safety_factor=1.1,
    )
    assert m["grid_step_pct"] is not None
    assert m["breakeven_ok"] is True
    assert m["recommended_grid_levels"] >= 2


def test_breakeven_false_and_recommend_levels():
    m = compute_breakeven_metrics(
        lower_price=86000,
        upper_price=90000,
        grid_levels=20,
        grid_type="geometric",
        fee_bps=20,
        spread_bps=10,
        slippage_bps=20,
        safety_factor=1.2,
    )
    assert m["breakeven_ok"] is False
    assert m["recommended_grid_levels"] < 20


def test_recommended_levels_clamped_minimum():
    m = compute_breakeven_metrics(
        lower_price=100,
        upper_price=101,
        grid_levels=3,
        grid_type="geometric",
        fee_bps=0,
        spread_bps=0,
        slippage_bps=0,
        safety_factor=1.2,
    )
    assert m["recommended_grid_levels"] >= 2
