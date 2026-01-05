import yaml
from pathlib import Path
from typing import Any, Dict

from .costs import grid_step_pct as _grid_step_pct_helper, recommend_grid_levels as _recommend_grid_levels_helper


DRY_RUN = True
CONFIG_FILE = Path("config.yaml")
DB_FILE = Path("grid_bot.db")


def estimate_roundtrip_cost_bps(fee_bps: float, spread_bps: float, slippage_bps: float) -> float:
    """Approximate round-trip cost in bps."""
    return 2 * float(fee_bps) + float(spread_bps) + float(slippage_bps)


def grid_step_pct(lower_price: float, upper_price: float, grid_levels: int, grid_type: str) -> float:
    """Estimate grid step percentage (fraction)."""
    return _grid_step_pct_helper(lower_price, upper_price, grid_levels, grid_type) or 0.0


def recommend_grid_levels(lower_price: float, upper_price: float, min_step_bps: float, grid_type: str) -> int:
    """Return max grid_levels to satisfy min_step_bps (geometric default)."""
    min_step_pct = float(min_step_bps) / 100 if min_step_bps is not None else 0.0
    return _recommend_grid_levels_helper(lower_price, upper_price, grid_type, min_step_pct)


def load_config(path: Path = CONFIG_FILE) -> Dict[str, Any]:
    """Load strategy settings required for the grid calculator."""
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing")

    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if not isinstance(data, dict):
        raise ValueError("config.yaml must contain a mapping at the root level")

    required = {"symbol", "grid_levels", "order_size"}
    missing = required.difference(data)
    if missing:
        raise ValueError(f"config.yaml missing required keys: {', '.join(sorted(missing))}")

    def _maybe_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    data["lower_price"] = _maybe_float(data.get("lower_price"))
    data["upper_price"] = _maybe_float(data.get("upper_price"))
    data["grid_levels"] = int(data["grid_levels"])
    data["order_size"] = float(data["order_size"])
    data["trailing_up"] = bool(data.get("trailing_up", False))
    data["stop_loss_enabled"] = bool(data.get("stop_loss_enabled", True))
    data["grid_type"] = str(data.get("grid_type", "arithmetic")).lower()
    data["csv_range_padding_pct"] = float(data.get("csv_range_padding_pct", 0.5))
    risk_cfg = data.get("risk", {})
    data["risk"] = {
        "enabled": bool(risk_cfg.get("enabled", True)),
        "max_consecutive_errors": int(risk_cfg.get("max_consecutive_errors", 5)),
        "max_price_jump_pct": float(risk_cfg.get("max_price_jump_pct", 3.0)),
        "pause_seconds": float(risk_cfg.get("pause_seconds", 60)),
        "max_drawdown_pct": float(risk_cfg.get("max_drawdown_pct", 10.0)),
        "panic_on_stop": bool(risk_cfg.get("panic_on_stop", True)),
        "amplitude_pct": float(risk_cfg.get("amplitude_pct", 1.0)),
        "noise_pct": float(risk_cfg.get("noise_pct", 0.5)),
        "period_steps": int(risk_cfg.get("period_steps", 24)),
        "risk_action": str(risk_cfg.get("risk_action", "EXIT")).upper(),
        "fail_if_unprofitable_grid": bool(risk_cfg.get("fail_if_unprofitable_grid", False)),
        "fail_if_below_breakeven": bool(risk_cfg.get("fail_if_below_breakeven", False)),
    }
    if data["risk"]["max_consecutive_errors"] < 1:
        data["risk"]["max_consecutive_errors"] = 1
    if data["risk"]["pause_seconds"] < 0:
        data["risk"]["pause_seconds"] = 0
    acct_cfg = data.get("accounting", {})
    data["accounting"] = {
        "enabled": bool(acct_cfg.get("enabled", True)),
        "initial_usdt": float(acct_cfg.get("initial_usdt", 1000.0)),
        "initial_base": float(acct_cfg.get("initial_base", 0.0)),
        "initial_inventory_mode": str(acct_cfg.get("initial_inventory_mode", "manual")).lower(),
        "initial_base_value_pct": float(acct_cfg.get("initial_base_value_pct", 0.5)),
        "fee_rate": float(acct_cfg.get("fee_rate", 0.001)),
        "fee_bps": float(acct_cfg.get("fee_bps", 0.0)),
        "slippage_bps": float(acct_cfg.get("slippage_bps", 0.0)),
        "spread_bps": float(acct_cfg.get("spread_bps", 0.0)),
        "maker_fee_bps": float(acct_cfg.get("maker_fee_bps", 0.0)),
        "taker_fee_bps": float(acct_cfg.get("taker_fee_bps", 0.0)),
        "apply_costs_in_price": bool(acct_cfg.get("apply_costs_in_price", True)),
    }
    data["strategy_id"] = str(data.get("strategy_id", "classic_grid"))
    data["offline"] = bool(data.get("offline", False))
    offline_prices = data.get("offline_prices", [])
    if isinstance(offline_prices, list):
        parsed_prices = []
        for price in offline_prices:
            try:
                parsed_prices.append(float(price))
            except (TypeError, ValueError):
                continue
        data["offline_prices"] = parsed_prices
    else:
        data["offline_prices"] = []
    exec_cfg = data.get("execution", {})
    if isinstance(exec_cfg, dict):
        data["execution"] = {
            "maker_taker_model": str(exec_cfg.get("maker_taker_model", "") or "").lower(),
            "maker_base_prob": float(exec_cfg.get("maker_base_prob", 1.0)),
            "volatility_penalty": float(exec_cfg.get("volatility_penalty", 0.0)),
        }
    else:
        data["execution"] = {}
    return data
