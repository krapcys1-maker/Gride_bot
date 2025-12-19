import yaml
from pathlib import Path
from typing import Any, Dict


DRY_RUN = True
CONFIG_FILE = Path("config.yaml")
DB_FILE = Path("grid_bot.db")


def load_config(path: Path = CONFIG_FILE) -> Dict[str, Any]:
    """Load strategy settings required for the grid calculator."""
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing")

    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if not isinstance(data, dict):
        raise ValueError("config.yaml must contain a mapping at the root level")

    required = {"symbol", "lower_price", "upper_price", "grid_levels", "order_size"}
    missing = required.difference(data)
    if missing:
        raise ValueError(f"config.yaml missing required keys: {', '.join(sorted(missing))}")

    data["lower_price"] = float(data["lower_price"])
    data["upper_price"] = float(data["upper_price"])
    data["grid_levels"] = int(data["grid_levels"])
    data["order_size"] = float(data["order_size"])
    data["trailing_up"] = bool(data.get("trailing_up", False))
    data["stop_loss_enabled"] = bool(data.get("stop_loss_enabled", True))
    data["grid_type"] = str(data.get("grid_type", "arithmetic")).lower()
    risk_cfg = data.get("risk", {})
    data["risk"] = {
        "enabled": bool(risk_cfg.get("enabled", True)),
        "max_consecutive_errors": int(risk_cfg.get("max_consecutive_errors", 5)),
        "max_price_jump_pct": float(risk_cfg.get("max_price_jump_pct", 3.0)),
        "pause_seconds": float(risk_cfg.get("pause_seconds", 60)),
        "max_drawdown_pct": float(risk_cfg.get("max_drawdown_pct", 10.0)),
        "panic_on_stop": bool(risk_cfg.get("panic_on_stop", True)),
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
        "fee_rate": float(acct_cfg.get("fee_rate", 0.001)),
        "slippage_bps": float(acct_cfg.get("slippage_bps", 0.0)),
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
    return data
