import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gridbot.app import main


BASE_CFG = Path("tests/fixtures/config_costs_neutral_maker100_nobase.yaml")


def test_panic_disabled_does_not_trigger(tmp_path):
    data = yaml.safe_load(BASE_CFG.read_text())
    data["panic_enabled"] = False
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(yaml.safe_dump(data))
    db_path = tmp_path / "bot.db"
    report_path = tmp_path / "report.json"
    csv_path = tmp_path / "panic_disable.csv"
    rows = ["open,high,low,close", "88000,88100,84000,84000", "84000,84100,83900,84050"]
    csv_path.write_text("\n".join(rows))
    args = [
        "--config",
        str(cfg_path),
        "--db-path",
        str(db_path),
        "--dry-run",
        "--offline",
        "--offline-scenario",
        "from_csv_ohlc",
        "--offline-csv",
        str(csv_path),
        "--seed",
        "1",
        "--max-steps",
        "10",
        "--interval",
        "0",
        "--reset-state",
        "--report-json",
        str(report_path),
    ]
    main(args)
    report = json.loads(report_path.read_text())
    assert report.get("reason") != "panic_sell"
    assert report.get("risk_state") != "PANIC"
