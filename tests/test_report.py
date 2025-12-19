import json
from pathlib import Path

from gridbot.app import main

FIXTURE_CONFIG = Path("tests/fixtures/config_small.yaml")


def run_with_report(tmp_path):
    report_path = tmp_path / "report.json"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(FIXTURE_CONFIG.read_text())
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
        "5",
        "--max-steps",
        "50",
        "--interval",
        "0",
        "--reset-state",
        "--report-json",
        str(report_path),
    ]
    main(args)
    return report_path


def test_report_json_created(tmp_path):
    report_path = run_with_report(tmp_path)
    assert report_path.exists()
    data = json.loads(report_path.read_text())
    assert "config_path" in data
    assert "metrics" in data
    metrics = data["metrics"]
    for key in ["trades", "total_fees", "equity", "pnl"]:
        assert key in metrics
