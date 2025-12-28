from pathlib import Path

from gridbot.tools.batch_run import main_cli


def test_batch_run_includes_grid_levels(tmp_path):
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
        "--grid-levels",
        "5,10",
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
    header = rows[0].split(",")
    assert "grid_levels_used" in header
    grid_idx = header.index("grid_levels_used")
    run_idx = header.index("run_id")
    data_rows = [r.split(",") for r in rows[1:]]
    grid_vals = {row[grid_idx] for row in data_rows}
    run_ids = {row[run_idx] for row in data_rows}
    assert "5" in grid_vals
    assert "10" in grid_vals
    assert any("gl5" in r for r in run_ids)
    assert any("gl10" in r for r in run_ids)
