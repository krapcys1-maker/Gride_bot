import json
from pathlib import Path

from gridbot.app import main


def test_offline_csv_ohlc_runs_and_trades(tmp_path):
    cfg_src = Path("tests/fixtures/config_costs.yaml")
    cfg = tmp_path / "config.yaml"
    import yaml

    data = yaml.safe_load(cfg_src.read_text())
    data.setdefault("accounting", {})["initial_base"] = 0.01
    cfg.write_text(yaml.safe_dump(data))
    report_path = tmp_path / "report.json"
    db_path = tmp_path / "bot.db"
    args = [
        "--dry-run",
        "--offline",
        "--offline-csv",
        "tests/fixtures/ohlc_small.csv",
        "--offline-once",
        "--max-steps",
        "20",
        "--interval",
        "0",
        "--reset-state",
        "--config",
        str(cfg),
        "--db-path",
        str(db_path),
        "--report-json",
        str(report_path),
    ]
    main(args)
    data = json.loads(report_path.read_text())
    assert data["steps_completed"] <= 20
    assert data["metrics"]["trades"] >= 1
