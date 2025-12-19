import json
from pathlib import Path

from gridbot.tools.batch_run import main_cli


def test_batch_run_outputs_cost_metrics(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    args = [
        "--strategy-ids",
        "classic_grid",
        "--scenarios",
        "range",
        "--seeds",
        "1",
        "--steps",
        "10",
        "--parallel",
        "1",
        "--out-dir",
        str(out_dir),
        "--config",
        "tests/fixtures/config_costs.yaml",
        "--interval",
        "0",
        "--log-level",
        "ERROR",
    ]
    main_cli(args)
    csv_path = out_dir / "results.csv"
    assert csv_path.exists()
    content = csv_path.read_text().splitlines()
    header = content[0].split(",")
    assert "grid_step_pct" in header
    assert "roundtrip_cost_pct" in header
    assert "breakeven_ok" in header
    assert "recommended_grid_levels" in header
