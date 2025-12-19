import yaml
from pathlib import Path

import pytest

from gridbot.core.bot import GridBot
from gridbot.core.costs import roundtrip_cost_bps, grid_step_pct, recommend_grid_levels


def _make_config(tmp_path, levels: int, fee_bps: float = 20.0, spread_bps: float = 10.0, slippage_bps: float = 20.0) -> Path:
    cfg = tmp_path / f"cfg_{levels}.yaml"
    data = {
        "symbol": "BTC/USDT",
        "lower_price": 86000,
        "upper_price": 90000,
        "grid_levels": levels,
        "order_size": 0.001,
        "grid_type": "geometric",
        "trailing_up": False,
        "stop_loss_enabled": True,
        "offline": True,
        "offline_prices": [88000, 88100, 87900],
        "risk": {"fail_if_unprofitable_grid": False},
        "accounting": {
            "enabled": True,
            "initial_usdt": 1000,
            "initial_base": 0,
            "fee_bps": fee_bps,
            "spread_bps": spread_bps,
            "slippage_bps": slippage_bps,
            "fee_rate": 0,
        },
    }
    cfg.write_text(yaml.safe_dump(data))
    return cfg


def test_unprofitable_grid_warns_and_recommends_levels(tmp_path, caplog):
    cfg = _make_config(tmp_path, levels=10, fee_bps=20, spread_bps=10, slippage_bps=20)  # 70 bps costs
    db_path = tmp_path / "bot.db"
    with caplog.at_level("WARNING"):
        bot = GridBot(config_path=cfg, db_path=db_path, dry_run=True, offline=True)
    # cost math sanity
    breakeven = roundtrip_cost_bps(20, 10, 20)
    step_pct = grid_step_pct(86000, 90000, 10, "geometric")
    assert step_pct * 10000 < breakeven * 1.2 * 100  # below safety threshold
    assert any("Grid step" in rec.message for rec in caplog.records)
    rec_levels = recommend_grid_levels(86000, 90000, "geometric", breakeven / 100 * 1.2 * 100)
    assert rec_levels < 10
    bot.close()


def test_profitable_grid_passes_guard(tmp_path, caplog):
    cfg = _make_config(tmp_path, levels=5, fee_bps=20, spread_bps=10, slippage_bps=20)
    db_path = tmp_path / "bot_ok.db"
    with caplog.at_level("WARNING"):
        bot = GridBot(config_path=cfg, db_path=db_path, dry_run=True, offline=True)
    assert not any("min_step_bps" in rec.message for rec in caplog.records)
    assert bot.status == "RUNNING"
    bot.close()


def test_unprofitable_grid_with_fail_flag_stops(tmp_path):
    cfg = _make_config(tmp_path, levels=10, fee_bps=20, spread_bps=10, slippage_bps=20)
    data = yaml.safe_load(Path(cfg).read_text())
    data.setdefault("risk", {})["fail_if_below_breakeven"] = True
    cfg.write_text(yaml.safe_dump(data))
    db_path = tmp_path / "bot_stop.db"
    bot = GridBot(config_path=cfg, db_path=db_path, dry_run=True, offline=True)
    report = bot.run(interval=0, max_steps=1)
    assert report["status"] == "STOPPED"
    assert report["reason"] == "unprofitable_grid"
    assert report["steps_completed"] in (0, 1)
    assert report["metrics"]["breakeven_ok"] is False
    assert report["metrics"]["recommended_grid_levels"] is not None
    bot.close()
