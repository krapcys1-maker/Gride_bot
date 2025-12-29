from pathlib import Path

from gridbot.tools.batch_run import main_cli


def test_batch_run_applies_set_overrides(tmp_path):
    out_dir = tmp_path / "out_override"
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
        "50",
        "--grid-levels",
        "3",
        "--config",
        "tests/fixtures/config_costs_neutral_maker100_nobase.yaml",
        "--offline-csv",
        "tests/fixtures/ohlc_touch.csv",
        "--interval",
        "0",
        "--log-level",
        "ERROR",
        "--set",
        "panic_enabled=false",
    ]
    main_cli(args)
    applied_cfg = out_dir / "applied_config.yaml"
    assert applied_cfg.exists()
    data = applied_cfg.read_text()
    assert "panic_enabled: false" in data
    cfg_files = list((out_dir / "configs").glob("*.yaml"))
    assert cfg_files
    cfg_data = cfg_files[0].read_text()
    assert "panic_enabled: false" in cfg_data
