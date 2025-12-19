import json
from pathlib import Path

from gridbot.app import main


def test_report_contains_cost_guard_metrics(tmp_path):
    cfg = Path("tests/fixtures/config_costs.yaml")
    report_path = tmp_path / "report.json"
    db_path = tmp_path / "bot.db"
    args = [
        "--dry-run",
        "--offline",
        "--offline-scenario",
        "range",
        "--seed",
        "1",
        "--max-steps",
        "50",
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
    metrics = data["metrics"]
    assert metrics["grid_step_pct"] is not None
    assert metrics["roundtrip_cost_bps"] == 70.0
    assert metrics["roundtrip_cost_pct"] is not None
    assert metrics["breakeven_ok"] is not None
