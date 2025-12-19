import json
from pathlib import Path

import yaml

from gridbot.app import main
from gridbot.core.bot import GridBot


def _run_report(tmp_path, base_cfg: Path, label: str, apply_costs_in_price: bool) -> dict:
    cfg = tmp_path / f"{label}_cfg.yaml"
    data = yaml.safe_load(base_cfg.read_text())
    data.setdefault("accounting", {}).update(
        {
            "apply_costs_in_price": apply_costs_in_price,
            "fee_bps": 10,
            "spread_bps": 20,
            "slippage_bps": 30,
            "fee_rate": 0,
            "maker_fee_bps": 0,
            "taker_fee_bps": 0,
        }
    )
    cfg.write_text(yaml.safe_dump(data))
    report_path = tmp_path / f"{label}.json"
    db_path = tmp_path / f"{label}.db"
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
        "200",
        "--interval",
        "0",
        "--reset-state",
        "--report-json",
        str(report_path),
    ]
    main(args)
    return json.loads(report_path.read_text())


def test_costs_in_price_only_fees_reduce_pnl(tmp_path):
    base_cfg = Path("tests/fixtures/config_costs.yaml")
    report = _run_report(tmp_path, base_cfg, "costs_in_price", apply_costs_in_price=True)
    metrics = report["metrics"]
    assert metrics["total_fees_quote"] > 0
    # slippage/spread are baked into execution price; net = gross - fees
    assert abs((metrics["pnl_gross"] - metrics["total_fees_quote"]) - metrics["pnl_net"]) < 1e-6


def test_costs_off_price_subtract_slip_and_spread(tmp_path):
    base_cfg = Path("tests/fixtures/config_costs.yaml")
    report = _run_report(tmp_path, base_cfg, "costs_off_price", apply_costs_in_price=False)
    metrics = report["metrics"]
    assert metrics["slippage_cost_est_quote"] > 0 or metrics["spread_cost_est_quote"] > 0
    lhs = (
        metrics["pnl_gross"]
        - metrics["total_fees_quote"]
        - metrics["slippage_cost_est_quote"]
        - metrics["spread_cost_est_quote"]
    )
    assert abs(lhs - metrics["pnl_net"]) < 1e-6


def test_costs_nonzero_when_enabled(tmp_path):
    base_cfg = Path("tests/fixtures/config_costs.yaml")
    report = _run_report(tmp_path, base_cfg, "nonzero", apply_costs_in_price=True)
    metrics = report["metrics"]
    assert metrics["total_fees_quote"] > 0
    assert metrics["slippage_cost_est_quote"] > 0
    assert metrics["spread_cost_est_quote"] > 0
    assert metrics["trades"] > 0


def test_report_identity_equity_pnl(tmp_path):
    base_cfg = Path("tests/fixtures/config_costs.yaml")
    report = _run_report(tmp_path, base_cfg, "identity", apply_costs_in_price=True)
    metrics = report["metrics"]
    eq_i = metrics["equity_initial"]
    eq_f = metrics["equity_final"]
    pnl = metrics["pnl_net"]
    assert eq_i is not None and eq_f is not None and pnl is not None
    assert abs((eq_i + pnl) - eq_f) < 1e-6


def test_grid_guard_reduces_levels_when_costs_high(tmp_path):
    cfg = Path("tests/fixtures/config_costs.yaml")
    db_path = tmp_path / "guard.db"
    bot = GridBot(config_path=cfg, db_path=db_path, dry_run=True, offline=True, offline_scenario="range")
    original_levels = bot.grid_levels
    bot._guard_grid_edge(price=88000.0)
    assert bot.grid_levels <= original_levels
    assert bot.grid_levels < original_levels  # adjusted down to restore edge
    bot.close()


def _config_with_levels(tmp_path, levels: int) -> Path:
    cfg = Path("tests/fixtures/config_costs.yaml")
    data = yaml.safe_load(cfg.read_text())
    data["grid_levels"] = levels
    data["risk"] = data.get("risk", {})
    data["risk"]["fail_if_below_breakeven"] = True
    data["offline"] = True
    data["offline_prices"] = [88000, 88100, 87900]
    new_cfg = tmp_path / f"cfg_levels_{levels}.yaml"
    new_cfg.write_text(yaml.safe_dump(data))
    return new_cfg


def test_cost_warning_triggers_when_step_below_costs(tmp_path, caplog):
    cfg = _config_with_levels(tmp_path, levels=10)
    db_path = tmp_path / "warn.db"
    with caplog.at_level("WARNING"):
        bot = GridBot(config_path=cfg, db_path=db_path, dry_run=True, offline=True, offline_scenario="range")
    bot.close()
    assert any("min_step_pct" in rec.message for rec in caplog.records)


def test_breakeven_ok_field(tmp_path):
    cfg = _config_with_levels(tmp_path, levels=10)
    db_path = tmp_path / "breakeven.db"
    bot = GridBot(config_path=cfg, db_path=db_path, dry_run=True, offline=True, offline_scenario="range")
    report = bot._final_report()
    metrics = report["metrics"]
    assert metrics["roundtrip_cost_bps"] == 70.0
    assert metrics["breakeven_ok"] is False
    bot.close()


def test_cost_warning_not_triggered_when_step_above_costs(tmp_path, caplog):
    cfg = _config_with_levels(tmp_path, levels=4)
    db_path = tmp_path / "warn_ok.db"
    with caplog.at_level("WARNING"):
        bot = GridBot(config_path=cfg, db_path=db_path, dry_run=True, offline=True, offline_scenario="range")
    bot.close()
    assert not any("negative expectation" in rec.message for rec in caplog.records)
