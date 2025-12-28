import json
from pathlib import Path

import yaml

from gridbot.app import main


BASE_CFG = Path("tests/fixtures/config_costs_neutral_maker100_nobase.yaml")


def test_panic_prevents_fills_on_flash_crash_nobase(tmp_path):
    data = yaml.safe_load(BASE_CFG.read_text())
    data["grid_levels"] = 4
    data["order_size"] = 10.0  # ensure no accidental fills
    cfg_path = tmp_path / "cfg.yaml"
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
        "flash_crash",
        "--seed",
        "5",
        "--max-steps",
        "2000",
        "--interval",
        "0",
        "--reset-state",
        "--report-json",
        str(report_path),
    ]
    main(args)
    report = json.loads(report_path.read_text())
    metrics = report["metrics"]
    assert metrics["trades"] == 0
    assert metrics["pnl_total"] == 0
    assert report["risk_state"] == "PANIC"
    assert report["risk_action"] == "NONE"
