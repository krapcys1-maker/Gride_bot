import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gridbot.tools import batch_run


def test_flash_crash_reason_is_panic_sell(tmp_path):
    out_dir = tmp_path / "out"
    cfg_path = REPO_ROOT / "tests/fixtures/config_costs_neutral_mix70_nobase.yaml"
    args = [
        "--out-dir",
        str(out_dir),
        "--strategy-ids",
        "classic_grid",
        "--scenarios",
        "flash_crash",
        "--seeds",
        "1",
        "--steps",
        "500",
        "--config",
        str(cfg_path),
        "--grid-levels",
        "4",
        "--interval",
        "0",
        "--log-level",
        "ERROR",
        "--set",
        "panic_enabled=true",
    ]
    batch_run.main_cli(args)
    results_path = out_dir / "results.csv"
    rows = list(csv.DictReader(results_path.read_text().splitlines()))
    assert rows
    row = rows[0]
    assert row["scenario"] == "flash_crash"
    assert row["reason"] == "panic_sell"
