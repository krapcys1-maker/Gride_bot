from pathlib import Path

from gridbot.tools.batch_run import main_cli
import pytest
import json


def test_batch_run_writes_results(tmp_path):
    out_dir = tmp_path / "runs"
    args = [
        "--out-dir",
        str(out_dir),
        "--strategy-ids",
        "classic_grid",
        "--scenarios",
        "range",
        "--seeds",
        "1,2",
        "--steps",
        "50",
        "--config",
        "tests/fixtures/config_small.yaml",
        "--interval",
        "0",
        "--log-level",
        "WARNING",
    ]
    main_cli(args)
    csv_path = out_dir / "results.csv"
    assert csv_path.exists()
    rows = csv_path.read_text().strip().splitlines()
    # header + at least 2 rows
    assert len(rows) >= 3


def test_batch_run_creates_stub_on_error(tmp_path, monkeypatch):
    # Make main do nothing and not create report file
    def fake_main(argv=None):
        return None

    monkeypatch.setattr("gridbot.tools.batch_run.main", fake_main)

    out_dir = tmp_path / "runs"
    args = [
        "--out-dir",
        str(out_dir),
        "--strategy-ids",
        "classic_grid",
        "--scenarios",
        "range",
        "--seeds",
        "1",
        "--steps",
        "10",
        "--config",
        "tests/fixtures/config_small.yaml",
        "--interval",
        "0",
        "--log-level",
        "WARNING",
    ]
    main_cli(args)
    csv_path = out_dir / "results.csv"
    assert csv_path.exists()
    rows = csv_path.read_text().strip().splitlines()
    assert len(rows) == 2
    # verify stub report created
    report_path = out_dir / "reports" / "classic_grid_range_seed1.json"
    assert report_path.exists()
    data = json.loads(report_path.read_text())
    assert data["status"] == "ERROR"


def test_batch_run_counts_total_runs_with_csv_args(tmp_path):
    out_dir = tmp_path / "runs2"
    args = [
        "--out-dir",
        str(out_dir),
        "--strategy-ids",
        "classic_grid",
        "--scenarios",
        "range,trend_up",
        "--seeds",
        "1,2",
        "--steps",
        "20",
        "--config",
        "tests/fixtures/config_small.yaml",
        "--interval",
        "0",
        "--log-level",
        "WARNING",
    ]
    main_cli(args)
    csv_path = out_dir / "results.csv"
    assert csv_path.exists()
    rows = csv_path.read_text().strip().splitlines()
    # header + 4 runs
    assert len(rows) == 1 + 4
