from pathlib import Path

from gridbot.core.bot import GridBot
import pytest
import yaml


def _make_bot(tmp_path, maker_prob: float, seed: int = 123) -> GridBot:
    cfg = {
        "symbol": "BTC/USDT",
        "lower_price": 86000,
        "upper_price": 90000,
        "grid_levels": 3,
        "order_size": 0.001,
        "trailing_up": False,
        "stop_loss_enabled": True,
        "grid_type": "geometric",
        "dry_run": True,
        "strategy_id": "classic_grid",
        "risk": {"enabled": True},
        "accounting": {"enabled": True, "initial_usdt": 1000.0, "initial_base": 0.0},
        "execution": {"maker_taker_model": "heuristic", "maker_base_prob": maker_prob, "volatility_penalty": 0.9},
    }
    cfg_path = tmp_path / f"cfg_{maker_prob}.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg))
    db_path = tmp_path / f"bot_{maker_prob}.db"
    return GridBot(config_path=cfg_path, db_path=db_path, dry_run=True, offline=True, seed=seed)


@pytest.mark.parametrize("maker_prob", [0.5, 0.7])
def test_maker_ratio_matches_base_prob(tmp_path, maker_prob):
    bot = _make_bot(tmp_path, maker_prob, seed=42)
    decisions = [bot._decide_maker(88000.0) for _ in range(5000)]
    ratio = sum(decisions) / len(decisions)
    assert abs(ratio - maker_prob) < 0.05


def test_maker_prob_one_is_always_maker(tmp_path):
    bot = _make_bot(tmp_path, 1.0, seed=99)
    decisions = [bot._decide_maker(88000.0) for _ in range(5000)]
    ratio = sum(decisions) / len(decisions)
    assert ratio == 1.0
