import json
from pathlib import Path

import pytest
import yaml

from gridbot.app import main


BASE_CFG = Path("tests/fixtures/config_costs_neutral_maker100_nobase.yaml")


def test_initial_base_and_equity_match_config(tmp_path):
    data = yaml.safe_load(BASE_CFG.read_text())
    data["grid_levels"] = 3
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(data))
    report_path = tmp_path / "report.json"
    db_path = tmp_path / "bot.db"
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
        "1",
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
    assert metrics["base_initial"] == 0
    assert metrics["equity_initial"] == pytest.approx(data["accounting"]["initial_quote"])
