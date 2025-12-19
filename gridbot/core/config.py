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
