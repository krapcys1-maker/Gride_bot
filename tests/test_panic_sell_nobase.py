import json
from pathlib import Path

import pytest
import yaml

from gridbot.app import main


BASE_CFG = Path("tests/fixtures/config_costs_neutral_maker100_nobase.yaml")


@pytest.mark.parametrize("grid_levels", [3, 5])
def test_flash_crash_nobase_does_not_panic_stop(tmp_path, grid_levels):
    data = yaml.safe_load(BASE_CFG.read_text())
    data["grid_levels"] = grid_levels
    cfg_path = tmp_path / f"config_gl{grid_levels}.yaml"
    cfg_path.write_text(yaml.safe_dump(data))
    db_path = tmp_path / "bot.db"
    report_path = tmp_path / f"report_gl{grid_levels}.json"
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
    assert report.get("status") == "STOPPED"
    assert report.get("reason") == "panic_sell"
    metrics = report.get("metrics", {})
    assert metrics.get("trades", 0) == 0
