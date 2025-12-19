import json
from pathlib import Path

from gridbot.app import main


def run_report(tmp_path, config_path: Path, label: str, spread_bps: float, slippage_bps: float, fee_bps: float):
    cfg = tmp_path / f"{label}_config.yaml"
    cfg.write_text(config_path.read_text())
    import yaml

    data = yaml.safe_load(cfg.read_text())
    data.setdefault("accounting", {}).update(
        {
            "spread_bps": spread_bps,
            "slippage_bps": slippage_bps,
            "fee_bps": fee_bps,
            "fee_rate": 0,
            "maker_fee_bps": 0,
            "taker_fee_bps": 0,
        }
    )
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
        "range",
        "--seed",
        "1",
        "--max-steps",
        "400",
        "--interval",
        "0",
        "--reset-state",
        "--report-json",
        str(report_path),
    ]
    main(args)
    return json.loads(report_path.read_text())


def test_costs_applied_reduce_pnl_and_report_costs(tmp_path):
    cfg_path = Path("tests/fixtures/config_costs.yaml")
    base = run_report(tmp_path, cfg_path, "base", spread_bps=0, slippage_bps=0, fee_bps=0)
    costly = run_report(tmp_path, cfg_path, "costly", spread_bps=20, slippage_bps=30, fee_bps=10)

    assert base["status"] != "ERROR" and costly["status"] != "ERROR"
    metrics_base = base["metrics"]
    metrics_costly = costly["metrics"]
    assert metrics_costly["total_fees"] > 0
    assert metrics_costly["total_slippage"] > 0 or metrics_costly["slippage_spread_cost_est"] > 0
    assert metrics_costly["pnl_net"] < metrics_base["pnl_net"]
    assert metrics_costly["pnl_gross"] > metrics_costly["pnl_net"]
