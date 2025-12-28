import json
from pathlib import Path

import yaml

from gridbot.app import main


BASE_CFG = Path("tests/fixtures/config_costs.yaml")
FEE_SPLIT_CFG = Path("tests/fixtures/config_costs_fee_split.yaml")


def _merge(dst, src):
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _merge(dst[key], value)
        else:
            dst[key] = value


def run_report(
    tmp_path,
    label: str,
    overrides=None,
    seed: int = 1,
    steps: int = 120,
    scenario: str = "range",
    base_cfg: Path = BASE_CFG,
) -> dict:
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
        scenario,
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


def test_all_maker_when_prob_one(tmp_path):
    overrides = {
        "accounting": {
            "maker_fee_bps": 5,
            "taker_fee_bps": 50,
            "fee_bps": 0,
            "fee_rate": 0,
        },
        "execution": {
            "maker_taker_model": "heuristic",
            "maker_base_prob": 1.0,
            "volatility_penalty": 0.0,
        },
    }
    report = run_report(tmp_path, "all_maker", overrides=overrides, seed=11, steps=150)
    metrics = report["metrics"]
    assert metrics["trades"] > 0
    assert metrics["maker_fills"] == metrics["trades"]
    assert metrics["taker_fills"] == 0
    assert metrics["maker_ratio"] == 1.0


def test_all_taker_when_prob_zero(tmp_path):
    overrides = {
        "accounting": {
            "maker_fee_bps": 0,
            "taker_fee_bps": 30,
            "fee_bps": 0,
            "fee_rate": 0,
        },
        "execution": {
            "maker_taker_model": "heuristic",
            "maker_base_prob": 0.0,
            "volatility_penalty": 0.0,
        },
    }
    report = run_report(tmp_path, "all_taker", overrides=overrides, seed=13, steps=150)
    metrics = report["metrics"]
    assert metrics["trades"] > 0
    assert metrics["maker_fills"] == 0
    assert metrics["taker_fills"] == metrics["trades"]
    assert metrics["maker_ratio"] == 0.0


def test_deterministic_maker_split(tmp_path):
    overrides = {
        "accounting": {
            "maker_fee_bps": 5,
            "taker_fee_bps": 15,
            "fee_bps": 0,
            "fee_rate": 0,
        },
        "execution": {
            "maker_taker_model": "heuristic",
            "maker_base_prob": 0.6,
            "volatility_penalty": 0.2,
        },
    }
    report1 = run_report(tmp_path, "det_a", overrides=overrides, seed=7, steps=160)
    report2 = run_report(tmp_path, "det_b", overrides=overrides, seed=7, steps=160)
    m1 = report1["metrics"]
    m2 = report2["metrics"]
    assert m1["maker_fills"] == m2["maker_fills"]
    assert m1["taker_fills"] == m2["taker_fills"]
    assert m1["maker_ratio"] == m2["maker_ratio"]
    assert abs(m1["pnl_net"] - m2["pnl_net"]) < 1e-9


def test_no_execution_section_defaults_to_maker(tmp_path):
    report = run_report(tmp_path, "no_exec", overrides={}, seed=5, steps=120)
    metrics = report["metrics"]
    assert metrics["trades"] > 0
    assert metrics["taker_fills"] == 0
    assert metrics["maker_fills"] == metrics["trades"]
    assert metrics["maker_ratio"] == 1.0
    eq_i = metrics["equity_initial"]
    eq_f = metrics["equity_final"]
    pnl_net = metrics["pnl_net"]
    pnl_gross = metrics["pnl_gross"]
    assert abs(eq_f - (eq_i + pnl_net)) < 1e-6
    assert abs((pnl_gross - pnl_net) - metrics["total_fees_quote"]) < 1e-6


def test_maker_vs_taker_fees_diverge(tmp_path):
    maker_overrides = {
        "execution": {
            "maker_taker_model": "heuristic",
            "maker_base_prob": 1.0,
            "volatility_penalty": 0.0,
        }
    }
    taker_overrides = {
        "execution": {
            "maker_taker_model": "heuristic",
            "maker_base_prob": 0.0,
            "volatility_penalty": 0.0,
        }
    }
    report_maker = run_report(
        tmp_path, "fees_maker", overrides=maker_overrides, seed=21, steps=160, base_cfg=FEE_SPLIT_CFG
    )
    report_taker = run_report(
        tmp_path, "fees_taker", overrides=taker_overrides, seed=21, steps=160, base_cfg=FEE_SPLIT_CFG
    )
    m1 = report_maker["metrics"]
    m2 = report_taker["metrics"]
    assert m1["trades"] > 0 and m2["trades"] > 0
    assert m1["trades"] == m2["trades"]
    assert m1["maker_ratio"] == 1.0
    assert m2["maker_ratio"] == 0.0
    assert m1["total_fees_quote"] < m2["total_fees_quote"]
