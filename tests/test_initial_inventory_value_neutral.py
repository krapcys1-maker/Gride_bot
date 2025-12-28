import json
from pathlib import Path

import pytest
import yaml

from gridbot.app import main


BASE_CFG = Path("tests/fixtures/config_small.yaml")


@pytest.mark.parametrize("base_pct", [0.25, 0.5])
def test_value_neutral_initial_inventory(tmp_path, base_pct):
    data = yaml.safe_load(BASE_CFG.read_text())
    data["accounting"]["initial_inventory_mode"] = "value_neutral"
    data["accounting"]["initial_base_value_pct"] = base_pct
    data["accounting"]["initial_usdt"] = 1000.0
    cfg_path = tmp_path / f"cfg_{int(base_pct*100)}.yaml"
    cfg_path.write_text(yaml.safe_dump(data))
    db_path = tmp_path / "bot.db"
    report_path = tmp_path / "report.json"
    args = [
        "--config",
        str(cfg_path),
        "--db-path",
        str(db_path),
        "--dry-run",
        "--offline",
        "--offline-scenario",
        "range",
        "--seed",
        "123",
        "--max-steps",
        "200",
        "--interval",
        "0",
        "--reset-state",
        "--report-json",
        str(report_path),
    ]
    main(args)
    report = json.loads(report_path.read_text())
    metrics = report["metrics"]
    start_price = metrics["start_price"]
    assert start_price is not None and start_price > 0
    expected_base_qty = 1000.0 * base_pct / start_price
    expected_quote = 1000.0 * (1 - base_pct)
    assert metrics["base_initial"] == pytest.approx(expected_base_qty, rel=1e-6)
    assert metrics["quote_initial"] == pytest.approx(expected_quote, rel=1e-9)
    assert metrics["equity_initial"] == pytest.approx(expected_quote + expected_base_qty * start_price, rel=1e-6)
