import json
from pathlib import Path

import pytest
import yaml

from gridbot.app import main


FIXTURE_CONFIG = Path("tests/fixtures/config_small.yaml")
FIXTURE_CSV = Path("tests/fixtures/ohlc_autorange.csv")


def _write_config(tmp_path: Path, include_bounds: bool, lower: float = None, upper: float = None) -> Path:
    data = yaml.safe_load(FIXTURE_CONFIG.read_text())
    if not include_bounds:
        data.pop("lower_price", None)
        data.pop("upper_price", None)
    else:
        if lower is not None:
            data["lower_price"] = lower
        if upper is not None:
            data["upper_price"] = upper
    data["offline"] = True
    data["offline_scenario"] = "from_csv_ohlc"
    data["offline_csv"] = str(FIXTURE_CSV)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(data))
    return cfg_path


def _run_bot(cfg_path: Path, report_path: Path, db_path: Path) -> dict:
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
        str(FIXTURE_CSV),
        "--offline-once",
        "--seed",
        "1",
        "--max-steps",
        "5",
        "--interval",
        "0",
        "--reset-state",
        "--report-json",
        str(report_path),
        "--log-level",
        "ERROR",
        "--status-every-seconds",
        "0",
    ]
    main(args)
    return json.loads(report_path.read_text())


def test_from_csv_ohlc_autorange_sets_bounds(tmp_path):
    cfg_path = _write_config(tmp_path, include_bounds=False)
    report_path = tmp_path / "report.json"
    report = _run_bot(cfg_path, report_path, tmp_path / "bot.db")
    metrics = report["metrics"]
    assert metrics["range_source"] == "csv_auto"
    assert metrics["raw_low"] == pytest.approx(90.0)
    assert metrics["raw_high"] == pytest.approx(190.0)
    assert metrics["lower_price_used"] == pytest.approx(90.0 * 0.995)
    assert metrics["upper_price_used"] == pytest.approx(190.0 * 1.005)
    assert metrics.get("inventory_only") is False
    assert metrics.get("start_outside_range") is False


def test_from_csv_ohlc_reports_start_outside_range(tmp_path):
    cfg_path = _write_config(tmp_path, include_bounds=True, lower=10.0, upper=20.0)
    report_path = tmp_path / "report.json"
    report = _run_bot(cfg_path, report_path, tmp_path / "bot2.db")
    metrics = report["metrics"]
    assert metrics["range_source"] == "config"
    assert metrics["lower_price_used"] == pytest.approx(10.0)
    assert metrics["upper_price_used"] == pytest.approx(20.0)
    assert metrics.get("start_outside_range") is True
    assert metrics.get("inventory_only") is False
