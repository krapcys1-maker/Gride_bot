import json
from pathlib import Path

import yaml

from gridbot.app import main


BASE_CFG = Path("tests/fixtures/config_costs_fee_split.yaml")


def _merge(dst, src):
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _merge(dst[key], value)
        else:
            dst[key] = value


def _run_report(tmp_path, label: str, maker_prob: float, seed: int = 1, steps: int = 180) -> dict:
    data = yaml.safe_load(BASE_CFG.read_text())
    overrides = {
        "execution": {
            "maker_taker_model": "heuristic",
            "maker_base_prob": maker_prob,
            "volatility_penalty": 0.0,
        }
    }
    _merge(data, overrides)
    cfg_path = tmp_path / f"{label}_config.yaml"
    cfg_path.write_text(yaml.safe_dump(data))
    db_path = tmp_path / f"{label}.db"
    report_path = tmp_path / f"{label}.json"
    args = [
        "--config",
        str(cfg_path),
        "--db-path",
        str(db_path),
        "--dry-run",
        "--offline",
        "--offline-scenario",
        "range",
        "--seed",
        str(seed),
        "--max-steps",
        str(steps),
        "--interval",
        "0",
        "--reset-state",
        "--report-json",
        str(report_path),
    ]
    main(args)
    return json.loads(report_path.read_text())


def test_maker_taker_fee_impact(tmp_path):
    report_maker = _run_report(tmp_path, "mt_maker", maker_prob=1.0, seed=1)
    report_taker = _run_report(tmp_path, "mt_taker", maker_prob=0.0, seed=1)
    m1 = report_maker["metrics"]
    m2 = report_taker["metrics"]
    assert m1["trades"] > 0
    assert m1["trades"] == m2["trades"]
    assert m1["maker_ratio"] == 1.0
    assert m2["maker_ratio"] == 0.0
    maker_fees = m1["total_fees_quote"]
    taker_fees = m2["total_fees_quote"]
    assert maker_fees < taker_fees * 0.5
    assert m1["pnl_net"] > m2["pnl_net"]
