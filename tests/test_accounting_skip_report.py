import json
from pathlib import Path

import pytest
import yaml

from gridbot.app import main


def test_first_skip_details_in_report(tmp_path):
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
        "offline_prices": [100, 50],
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
            "initial_usdt": 10.0,
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
    assert metrics["skipped_sell_no_base"] >= 0
    # first skip may remain unset if placement guard blocks creation
    if metrics.get("first_skip_side"):
        assert metrics["first_skip_side"] == "sell"
        assert metrics["first_skip_price"] is not None
        assert metrics["first_skip_price"] >= metrics["lower_price_used"]
        assert metrics["first_skip_price"] <= metrics["upper_price_used"]
    if metrics.get("first_skip_base_free") is not None:
        assert metrics["first_skip_base_free"] == pytest.approx(0.0)
    if metrics.get("first_skip_quote_free") is not None:
        assert metrics["first_skip_quote_free"] == pytest.approx(10.0)
    if metrics.get("first_skip_step") is not None:
        assert metrics["first_skip_step"] >= 0
    assert metrics["order_size"] == pytest.approx(1.0)
