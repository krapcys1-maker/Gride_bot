from gridbot.core.accounting import Accounting, AccountingConfig


def test_buy_sell_updates_balances_and_equity():
    acct = Accounting(
        AccountingConfig(
            initial_usdt=1000.0,
            initial_base=0.0,
            fee_rate=0.001,
            maker_fee_bps=10.0,
        )
    )
    ok, fee, eq = acct.on_fill("buy", price=100.0, qty=2.0)
    assert ok
    assert round(acct.base_qty, 6) == 2.0
    assert acct.quote_qty < 1000.0
    assert fee == 100.0 * 2.0 * 0.001
    equity_after_buy = eq

    ok, fee_sell, eq2 = acct.on_fill("sell", price=120.0, qty=1.0)
    assert ok
    assert round(acct.base_qty, 6) == 1.0
    assert eq2 > equity_after_buy  # profit on sell
    assert fee_sell == 120.0 * 1.0 * 0.001


def test_insufficient_balance_blocks_fill():
    acct = Accounting(AccountingConfig(initial_usdt=10.0, initial_base=0.0, fee_rate=0.001))
    ok, _, _ = acct.on_fill("buy", price=100.0, qty=1.0)
    assert not ok  # not enough quote
    acct = Accounting(AccountingConfig(initial_usdt=0.0, initial_base=0.0, fee_rate=0.001))
    ok, _, _ = acct.on_fill("sell", price=100.0, qty=1.0)
    assert not ok  # not enough base
