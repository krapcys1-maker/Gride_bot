import json
from pathlib import Path

import yaml

from gridbot.app import main
from gridbot.core.storage import Storage


def test_sell_skip_guard_offline(tmp_path):
    cfg = {
        "symbol": "BTC/USDT",
        "lower_price": 50,
        "upper_price": 100,
        "grid_levels": 3,
        "order_size": 1.0,
        "trailing_up": False,
        "stop_loss_enabled": True,
        "grid_type": "arithmetic",
        "dry_run": True,
        "strategy_id": "classic_grid",
        "offline": True,
        "offline_once": True,
        "offline_prices": [75, 75],
        "risk": {
            "enabled": True,
            "max_price_jump_pct": 1000,
            "pause_seconds": 0,
            "max_consecutive_errors": 5,
            "max_drawdown_pct": 100,
            "panic_on_stop": False,
        },
        "accounting": {
            "enabled": True,
            "initial_usdt": 1000.0,
            "initial_base": 0.0,
            "fee_bps": 0.0,
            "spread_bps": 0.0,
            "slippage_bps": 0.0,
            "apply_costs_in_price": True,
        },
    }
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg))
    report_path = tmp_path / "report.json"
    args = [
        "--config",
        str(cfg_path),
        "--db-path",
        str(tmp_path / "bot.db"),
        "--dry-run",
        "--offline",
        "--max-steps",
        "5",
        "--interval",
        "0",
        "--reset-state",
        "--report-json",
        str(report_path),
        "--log-level",
        "ERROR",
        "--status-every-seconds",
        "0",
    ]
    main(args)
    data = json.loads(report_path.read_text())
    metrics = data["metrics"]
    assert metrics["skipped_place_sell_no_base"] >= 1
    assert metrics["first_skip_side"] in {None, "sell", "buy"}
    assert metrics["order_size"] == 1.0
    assert metrics["equity"] == metrics["equity_initial"] == 1000.0
    # no sell orders persisted when base is insufficient
    storage = Storage(tmp_path / "bot.db")
    orders = storage.load_active_orders(order_size=1.0, exchange_id="offline")
    storage.close()
    assert all(o["side"].lower() != "sell" for o in orders)
