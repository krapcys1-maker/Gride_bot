import json
from pathlib import Path

import yaml

from gridbot.app import main


BASE_CFG = Path("tests/fixtures/config_costs_neutral_maker100_nobase.yaml")


def test_flash_crash_nobase_preserves_equity(tmp_path):
    data = yaml.safe_load(BASE_CFG.read_text())
    data["grid_levels"] = 3
    cfg_path = tmp_path / "config.yaml"
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
        "6",
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
    trades = metrics["trades"]
    pnl_net = metrics["pnl_net"]
    eq_i = metrics["equity_initial"]
    eq_f = metrics["equity_final"]
    assert trades <= 1
    assert abs(pnl_net or 0.0) < 1e-9
    assert eq_i is not None and eq_f is not None
    assert abs(eq_f - eq_i) < 1e-9
