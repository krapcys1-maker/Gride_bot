from gridbot.core.execution_model import ExecutionModel


def test_buy_not_filled_when_low_above_level():
    em = ExecutionModel(spread_bps=10, slippage_bps=5)
    assert em.should_fill_limit("buy", level_price=100, candle_low=101, candle_high=105) is False


def test_sell_not_filled_when_high_below_level():
    em = ExecutionModel(spread_bps=10, slippage_bps=5)
    assert em.should_fill_limit("sell", level_price=100, candle_low=95, candle_high=99) is False


def test_fill_price_adjusts_for_costs():
    em = ExecutionModel(spread_bps=10, slippage_bps=20)
    buy_price = em.fill_price_limit("buy", level_price=100)
    sell_price = em.fill_price_limit("sell", level_price=100)
    assert buy_price > 100
    assert sell_price < 100
