import json
from pathlib import Path

import yaml

from gridbot.app import main


BASE_CFG = Path("tests/fixtures/config_costs.yaml")
MAKER_CFG = Path("tests/fixtures/config_costs_neutral_maker100.yaml")
MIX_CFG = Path("tests/fixtures/config_costs_neutral_mix50.yaml")


def _merge(dst, src):
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _merge(dst[key], value)
        else:
            dst[key] = value


def run_report(tmp_path, label: str, base_cfg: Path, overrides=None, seed: int = 1, steps: int = 200) -> dict:
    overrides = overrides or {}
    data = yaml.safe_load(base_cfg.read_text())
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


def test_pnl_cost_decomposition(tmp_path):
    overrides = {"accounting": {"apply_costs_in_price": False}}
    report = run_report(tmp_path, "decomp", base_cfg=BASE_CFG, overrides=overrides, seed=3, steps=180)
    m = report["metrics"]
    pnl_net = m["pnl_net"]
    pnl_gross = m["pnl_gross"]
    fees = m["total_fees_quote"]
    spread = m["spread_cost_est_quote"]
    slippage = m["slippage_cost_est_quote"]
    assert pnl_net is not None and pnl_gross is not None
    lhs = pnl_gross - pnl_net
    rhs = fees + spread + slippage
    assert abs(lhs - rhs) < 1e-6


def test_maker_ratio_affects_fees_only(tmp_path):
    maker_report = run_report(tmp_path, "maker_only", base_cfg=MAKER_CFG, seed=5, steps=200)
    mix_report = run_report(tmp_path, "maker_mix", base_cfg=MIX_CFG, seed=5, steps=200)
    m1 = maker_report["metrics"]
    m2 = mix_report["metrics"]
    assert m1["trades"] == m2["trades"] and m1["trades"] > 0
    assert m1["maker_ratio"] == 1.0
    assert m2["maker_ratio"] is not None and 0.0 < m2["maker_ratio"] < 1.0
    # Spread and slippage estimates should be identical for identical feed/seed.
    assert abs(m1["spread_cost_est_quote"] - m2["spread_cost_est_quote"]) < 1e-9
    assert abs(m1["slippage_cost_est_quote"] - m2["slippage_cost_est_quote"]) < 1e-9
    fee_diff = m2["total_fees_quote"] - m1["total_fees_quote"]
    pnl_delta = m1["pnl_net"] - m2["pnl_net"]
    assert fee_diff > 0
    assert abs(pnl_delta - fee_diff) < 1e-6
