import pytest
import yaml

from gridbot.tools.batch_run import main_cli


def test_cost_preset_applied_and_overridable(tmp_path):
    out_dir = tmp_path / "runs_cost_preset"
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
        "5",
        "--config",
        "tests/fixtures/config_small.yaml",
        "--interval",
        "0",
        "--log-level",
        "ERROR",
        "--cost-preset",
        "baseline",
        "--set",
        "accounting.maker_fee_bps=5",
    ]
    main_cli(args)
    applied_cfg = yaml.safe_load((out_dir / "applied_config.yaml").read_text())
    acct = applied_cfg["accounting"]
    assert acct["spread_bps"] == 20.0
    assert acct["slippage_bps"] == 30.0
    assert acct["taker_fee_bps"] == 8.0
    assert acct["maker_fee_bps"] == 5.0  # overridden by --set


def test_cost_preset_recorded_in_results_csv(tmp_path):
    """Verify cost_preset_used appears in results.csv."""
    out_dir = tmp_path / "runs_preset_csv"
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
        "5",
        "--config",
        "tests/fixtures/config_small.yaml",
        "--interval",
        "0",
        "--log-level",
        "ERROR",
        "--cost-preset",
        "medium",
    ]
    main_cli(args)
    csv_path = out_dir / "results.csv"
    lines = csv_path.read_text().strip().splitlines()
    header = lines[0].split(",")
    assert "cost_preset_used" in header
    idx = header.index("cost_preset_used")
    data_row = lines[1].split(",")
    assert data_row[idx] == "medium"


def test_cost_preset_metadata_in_applied_config(tmp_path):
    """Verify _batch_run_meta includes cost_preset_used."""
    out_dir = tmp_path / "runs_preset_meta"
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
        "5",
        "--config",
        "tests/fixtures/config_small.yaml",
        "--interval",
        "0",
        "--log-level",
        "ERROR",
        "--cost-preset",
        "ultra",
    ]
    main_cli(args)
    applied_cfg = yaml.safe_load((out_dir / "applied_config.yaml").read_text())
    assert "_batch_run_meta" in applied_cfg
    assert applied_cfg["_batch_run_meta"]["cost_preset_used"] == "ultra"


def test_conflicting_padding_flags_rejected(tmp_path):
    """Using both --csv-range-padding-pct and --set csv_range_padding_pct should fail."""
    out_dir = tmp_path / "runs_conflict"
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
        "5",
        "--config",
        "tests/fixtures/config_small.yaml",
        "--interval",
        "0",
        "--log-level",
        "ERROR",
        "--csv-range-padding-pct",
        "0.5",
        "--set",
        "csv_range_padding_pct=0.3",
    ]
    with pytest.raises(SystemExit) as exc_info:
        main_cli(args)
    assert "Cannot use both" in str(exc_info.value) or exc_info.value.code != 0
