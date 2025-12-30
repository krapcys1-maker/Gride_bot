import csv
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gridbot.core.costs import compute_grid_step_pct, grid_step_pct, recommend_grid_levels


def test_grid_step_pct_decreases_with_more_levels():
    lower = 100.0
    upper = 200.0
    step3 = grid_step_pct(lower, upper, 4, "geometric")  # levels-1 intervals
    step4 = grid_step_pct(lower, upper, 5, "geometric")
    assert step3 is not None and step4 is not None
    assert step4 < step3


def test_recommend_levels_caps_current():
    lower = 100.0
    upper = 200.0
    min_step_pct = 30.0
    rec = recommend_grid_levels(lower, upper, "geometric", min_step_pct)
    assert rec >= 2
    assert rec <= 4  # with current range and min step, 4 levels are too fine


def test_results_grid_step_matches_helper(tmp_path):
    out_dir = tmp_path / "out"
    cfg_path = REPO_ROOT / "tests/fixtures/config_costs_neutral_maker100_nobase.yaml"
    cmd = [
        sys.executable,
        "-m",
        "gridbot.tools.batch_run",
        "--out-dir",
        str(out_dir),
        "--scenarios",
        "range",
        "--seeds",
        "1",
        "--steps",
        "1",
        "--interval",
        "0",
        "--config",
        str(cfg_path),
        "--log-level",
        "ERROR",
    ]
    subprocess.run(cmd, check=True, cwd=REPO_ROOT)
    results_path = out_dir / "results.csv"
    rows = list(csv.DictReader(results_path.read_text().splitlines()))
    assert rows
    row = rows[0]
    levels_effective = int(row["grid_levels_effective"])
    cfg = yaml.safe_load(cfg_path.read_text())
    expected = compute_grid_step_pct(cfg["lower_price"], cfg["upper_price"], levels_effective, cfg.get("grid_type", "geometric"))
    assert expected is not None
    actual = float(row["grid_step_pct"])
    assert abs(actual - expected) < 1e-6
