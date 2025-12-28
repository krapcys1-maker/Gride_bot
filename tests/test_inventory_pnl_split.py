import json
from pathlib import Path

import pytest
import yaml

from gridbot.app import main


BASE_CFG = Path("tests/fixtures/config_costs_neutral_maker100.yaml")
NOBASE_CFG = Path("tests/fixtures/config_costs_neutral_maker100_nobase.yaml")


def _run(cfg_path: Path, tmp_path: Path, order_size: float) -> dict:
    data = yaml.safe_load(cfg_path.read_text())
    data["grid_levels"] = 3
    data["order_size"] = order_size
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.safe_dump(data))
    db_path = tmp_path / "bot.db"
    report_path = tmp_path / "report.json"
    args = [
        "--config",
        str(cfg),
        "--db-path",
        str(db_path),
        "--dry-run",
        "--offline",
        "--offline-scenario",
        "flash_crash",
        "--seed",
        "6",
        "--max-steps",
        "400",
        "--interval",
        "0",
        "--reset-state",
        "--report-json",
        str(report_path),
    ]
    main(args)
    return json.loads(report_path.read_text())


def test_inventory_drawdown_reason_when_no_trades(tmp_path):
    # start with base only, zero quote so buys cannot fill; panic stop -> inventory_drawdown
    data = yaml.safe_load(BASE_CFG.read_text())
    data["accounting"]["initial_usdt"] = 0
    data["accounting"]["initial_quote"] = 0
    cfg = tmp_path / "cfg_base_only.yaml"
    cfg.write_text(yaml.safe_dump(data))
    report = _run(cfg, tmp_path, order_size=0.001)
    assert report["status"] == "STOPPED"
    assert report["reason"] == "inventory_drawdown"
    assert report["risk_state"] == "PANIC"
    assert report["risk_action"] == "PANIC_SELL_EXECUTED"
    metrics = report["metrics"]
    assert metrics["inventory_only"] is True
    assert metrics["pnl_total"] is not None
    assert metrics["pnl_trading"] is not None
    assert metrics["pnl_inventory_mtm"] == pytest.approx(metrics["pnl_total"] - metrics["pnl_trading"])
    assert metrics["trades"] == 0


def test_nobase_zero_trades_pnl_split(tmp_path):
    report = _run(NOBASE_CFG, tmp_path, order_size=100.0)
    metrics = report["metrics"]
    assert report["status"] == "STOPPED"
    assert report["reason"] == "panic_sell"
    assert report["risk_state"] == "PANIC"
    assert report["risk_action"] == "NONE"
    assert metrics["trades"] == 0
    assert metrics["pnl_total"] == pytest.approx(0.0)
    assert metrics["pnl_trading"] == pytest.approx(0.0)
    assert metrics["pnl_inventory_mtm"] == pytest.approx(0.0)
