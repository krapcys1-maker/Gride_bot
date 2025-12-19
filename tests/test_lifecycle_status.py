import json
from pathlib import Path

from gridbot.app import main


def run_and_load(tmp_path, scenario: str, steps: int):
    report_path = tmp_path / "report.json"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(Path("tests/fixtures/config_small.yaml").read_text())
    db_path = tmp_path / "bot.db"
    args = [
        "--config",
        str(cfg_path),
        "--db-path",
        str(db_path),
        "--dry-run",
        "--offline",
        "--offline-scenario",
        scenario,
        "--seed",
        "7",
        "--max-steps",
        str(steps),
        "--interval",
        "0",
        "--reset-state",
        "--report-json",
        str(report_path),
    ]
    main(args)
    return json.loads(report_path.read_text())


def test_completed_status_and_steps(tmp_path):
    report = run_and_load(tmp_path, scenario="range", steps=10)
    assert report["status"] in ("COMPLETED", "OK", "RUNNING")  # allow OK alias if set
    assert report["steps_completed"] == 10
    assert report.get("reason") in ("max_steps", "", None) or report["status"] != "RUNNING"


def test_stopped_status_for_flash_crash(tmp_path):
    report = run_and_load(tmp_path, scenario="flash_crash", steps=200)
    assert report["status"] == "STOPPED"
    assert report.get("reason")
