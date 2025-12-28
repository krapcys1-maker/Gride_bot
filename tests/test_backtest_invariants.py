import json
from pathlib import Path

import yaml

from gridbot.app import main


FIXTURE_CFG = Path("tests/fixtures/config_costs.yaml")
NO_TOUCH_CSV = Path("tests/fixtures/ohlc_no_touch.csv")


def _merge(dst, src):
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _merge(dst[key], value)
        else:
            dst[key] = value


def _run_offline_report(tmp_path, label: str, overrides=None, offline_args=None, max_steps: int = 200) -> dict:
    data = yaml.safe_load(FIXTURE_CFG.read_text())
    overrides = overrides or {}
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
        "--max-steps",
        str(max_steps),
        "--interval",
        "0",
        "--reset-state",
        "--report-json",
        str(report_path),
    ]
    if offline_args:
        args.extend(offline_args)
    main(args)
    return json.loads(report_path.read_text())


def test_no_touch_no_fill(tmp_path):
    report = _run_offline_report(
        tmp_path,
        "no_touch",
        offline_args=[
            "--offline-csv",
            str(NO_TOUCH_CSV),
            "--offline-once",
        ],
        max_steps=20,
    )
    assert report["metrics"]["trades"] == 0


def test_equity_invariant(tmp_path):
    report = _run_offline_report(
        tmp_path,
        "equity_invariant",
        offline_args=[
            "--offline-scenario",
            "range",
            "--seed",
            "42",
        ],
        max_steps=150,
    )
    metrics = report["metrics"]
    eq_i = metrics["equity_initial"]
    eq_f = metrics["equity_final"]
    pnl_net = metrics["pnl_net"]
    assert eq_i is not None and eq_f is not None and pnl_net is not None
    assert abs(eq_f - (eq_i + pnl_net)) < 1e-6


def test_no_double_counting_costs(tmp_path):
    overrides = {
        "accounting": {
            "apply_costs_in_price": False,
            "fee_bps": 12,
            "spread_bps": 15,
            "slippage_bps": 25,
            "fee_rate": 0,
            "maker_fee_bps": 0,
            "taker_fee_bps": 0,
        }
    }
    report = _run_offline_report(
        tmp_path,
        "cost_decomp",
        overrides=overrides,
        offline_args=[
            "--offline-scenario",
            "range",
            "--seed",
            "7",
        ],
        max_steps=200,
    )
    metrics = report["metrics"]
    assert metrics["trades"] > 0
    pnl_gross = metrics["pnl_gross"]
    pnl_net = metrics["pnl_net"]
    assert pnl_gross is not None and pnl_net is not None
    cost_components = (
        (metrics.get("total_fees_quote") or 0.0)
        + (metrics.get("slippage_cost_est_quote") or 0.0)
        + (metrics.get("spread_cost_est_quote") or 0.0)
    )
    assert cost_components > 0
    assert abs((pnl_gross - pnl_net) - cost_components) < 1e-6
