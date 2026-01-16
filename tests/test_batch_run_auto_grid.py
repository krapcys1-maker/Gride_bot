import pytest
import yaml

from gridbot.core.costs import recommend_grid_levels, compute_grid_step_pct
from gridbot.tools.batch_run import main_cli


def test_auto_grid_levels_from_csv(tmp_path):
    out_dir = tmp_path / "runs_auto_grid"
    args = [
        "--out-dir",
        str(out_dir),
        "--strategy-ids",
        "classic_grid",
        "--scenarios",
        "from_csv_ohlc",
        "--seeds",
        "1",
        "--steps",
        "5",
        "--config",
        "tests/fixtures/config_costs_neutral_mix70_nobase_autorange.yaml",
        "--offline-csv",
        "tests/fixtures/ohlc_autorange.csv",
        "--interval",
        "0",
        "--log-level",
        "ERROR",
        "--auto-grid-levels",
        "--min-step-pct",
        "5",
    ]
    main_cli(args)
    csv_path = out_dir / "results.csv"
    rows = csv_path.read_text().strip().splitlines()
    header = rows[0].split(",")
    run_id_idx = header.index("run_id")
    grid_idx = header.index("grid_levels_used")
    grid_values = {row.split(",")[grid_idx] for row in rows[1:]}
    run_ids = {row.split(",")[run_id_idx] for row in rows[1:]}
    # expected levels based on CSV (90-190) with padding 0.5% and min_step_pct=5
    expected_levels = recommend_grid_levels(90 * 0.995, 190 * 1.005, "geometric", 5)
    assert grid_values == {str(expected_levels)}
    assert any(f"gl{expected_levels}" in r for r in run_ids)
    applied_cfg = yaml.safe_load((out_dir / "applied_config.yaml").read_text())
    assert applied_cfg["grid_levels"] == expected_levels


def test_auto_grid_fails_when_min_step_unsatisfiable(tmp_path):
    """min_step_pct too high for range should fail-fast with clear error."""
    out_dir = tmp_path / "runs_unsatisfiable"
    # The fixture has 90-190 range (~2.1x), max possible step is ~113%
    # Asking for 150% should fail
    args = [
        "--out-dir",
        str(out_dir),
        "--strategy-ids",
        "classic_grid",
        "--scenarios",
        "from_csv_ohlc",
        "--seeds",
        "1",
        "--steps",
        "5",
        "--config",
        "tests/fixtures/config_costs_neutral_mix70_nobase_autorange.yaml",
        "--offline-csv",
        "tests/fixtures/ohlc_autorange.csv",
        "--interval",
        "0",
        "--log-level",
        "ERROR",
        "--auto-grid-levels",
        "--min-step-pct",
        "150",  # impossible - max achievable is ~113% for this range
    ]
    with pytest.raises(SystemExit) as exc_info:
        main_cli(args)
    # Should fail with a clear message about unsatisfiable constraint
    assert exc_info.value.code != 0 or "Cannot satisfy" in str(exc_info.value)


def test_recommend_grid_levels_strict_raises_on_unsatisfiable():
    """Direct test of recommend_grid_levels with strict=True."""
    lower = 90 * 0.995
    upper = 190 * 1.005
    # With 2x range, max possible step is ~100% for geometric
    # Asking for 200% should fail
    with pytest.raises(ValueError) as exc_info:
        recommend_grid_levels(lower, upper, "geometric", 200.0, strict=True)
    assert "Cannot satisfy min_step_pct" in str(exc_info.value)


def test_recommend_grid_levels_strict_passes_when_satisfiable():
    """Direct test that strict=True works for satisfiable constraints."""
    lower = 90 * 0.995
    upper = 190 * 1.005
    levels = recommend_grid_levels(lower, upper, "geometric", 5.0, strict=True)
    actual_step = compute_grid_step_pct(lower, upper, levels, "geometric")
    assert actual_step >= 5.0


def test_auto_grid_includes_metadata_in_applied_config(tmp_path):
    """Verify applied_config.yaml includes _batch_run_meta section."""
    out_dir = tmp_path / "runs_metadata"
    args = [
        "--out-dir",
        str(out_dir),
        "--strategy-ids",
        "classic_grid",
        "--scenarios",
        "from_csv_ohlc",
        "--seeds",
        "1",
        "--steps",
        "5",
        "--config",
        "tests/fixtures/config_costs_neutral_mix70_nobase_autorange.yaml",
        "--offline-csv",
        "tests/fixtures/ohlc_autorange.csv",
        "--interval",
        "0",
        "--log-level",
        "ERROR",
        "--auto-grid-levels",
        "--min-step-pct",
        "5",
    ]
    main_cli(args)
    applied_cfg = yaml.safe_load((out_dir / "applied_config.yaml").read_text())
    assert "_batch_run_meta" in applied_cfg
    meta = applied_cfg["_batch_run_meta"]
    assert meta["auto_grid_levels_used"] is True
    assert meta["min_step_pct"] == 5.0
    assert "timestamp" in meta
    assert "auto_bounds" in meta
