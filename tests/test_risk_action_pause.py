import json
from pathlib import Path

from gridbot.app import main


def test_flash_crash_pause_stops_without_panic_sell(tmp_path):
    cfg_src = Path("tests/fixtures/config_batch.yaml")
    cfg = tmp_path / "config.yaml"
    data = cfg_src.read_text()
    cfg.write_text(data)
    import yaml

    yaml_data = yaml.safe_load(cfg.read_text())
    yaml_data.setdefault("risk", {})["risk_action"] = "PAUSE"
    cfg.write_text(yaml.safe_dump(yaml_data))

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
        "8",
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
    assert report["status"] == "STOPPED"
    assert report.get("reason") == "panic_pause"
    # ensure base holdings unchanged by panic sell (no forced liquidation)
