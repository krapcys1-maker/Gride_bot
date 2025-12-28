import json
from pathlib import Path

from gridbot.app import main
import yaml


TOUCH_CSV = Path("tests/fixtures/ohlc_touch.csv")
CFG_MAKER = Path("tests/fixtures/config_costs_neutral_maker100.yaml")
CFG_MIX50 = Path("tests/fixtures/config_costs_neutral_mix50.yaml")
CFG_MIX70 = Path("tests/fixtures/config_costs_neutral_mix70.yaml")


def _run(cfg_path: Path, tmp_path: Path, label: str, steps: int = 2000) -> dict:
    data = yaml.safe_load(cfg_path.read_text())
    data["grid_levels"] = 5
    data["order_size"] = 0.001
    data["stop_loss_enabled"] = False
    data["accounting"]["fee_bps"] = 0
    data["accounting"]["slippage_bps"] = 0
    data["accounting"]["spread_bps"] = 0
    data["accounting"]["maker_fee_bps"] = 0
    data["accounting"]["taker_fee_bps"] = 0
    data.setdefault("execution", {})
    data["execution"]["panic_on_range_break"] = False
    cfg = tmp_path / f"{label}_cfg.yaml"
    cfg.write_text(yaml.safe_dump(data))
    db_path = tmp_path / f"{label}.db"
    report_path = tmp_path / f"{label}.json"
    args = [
        "--config",
        str(cfg),
        "--db-path",
        str(db_path),
        "--dry-run",
        "--offline",
        "--offline-scenario",
        "from_csv_ohlc",
        "--offline-csv",
        str(TOUCH_CSV),
        "--seed",
        "5",
        "--max-steps",
        str(steps),
        "--interval",
        "0",
        "--reset-state",
        "--report-json",
        str(report_path),
    ]
    main(args)
    return json.loads(report_path.read_text())["metrics"]


def test_maker_ratio_tracks_probabilities(tmp_path):
    maker_metrics = _run(CFG_MAKER, tmp_path, "maker", steps=2000)
    mix50_metrics = _run(CFG_MIX50, tmp_path, "mix50", steps=2000)
    mix70_metrics = _run(CFG_MIX70, tmp_path, "mix70", steps=2000)

    assert maker_metrics["trades"] > 0
    assert mix50_metrics["trades"] > 0
    assert mix70_metrics["trades"] > 0

    assert maker_metrics["maker_ratio"] == 1.0
    ratio50 = mix50_metrics["maker_ratio"]
    ratio70 = mix70_metrics["maker_ratio"]
    assert 0.35 <= ratio50 <= 0.65
    assert abs(ratio50 - 0.5) < abs(ratio50 - 0.2)
    assert abs(ratio70 - 0.7) < abs(ratio70 - 0.5)
