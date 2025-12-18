from pathlib import Path
from typing import Any, Dict

import ccxt
import yaml


CONFIG_FILE = Path(__file__).with_name("config.yaml")


def load_config(path: Path = CONFIG_FILE) -> Dict[str, Any]:
    """Read YAML configuration and enforce required values."""
    if not path.exists():
        raise FileNotFoundError(f"{path} missing")

    parsed = yaml.safe_load(path.read_text())
    if not isinstance(parsed, dict):
        raise ValueError("config.yaml must contain a mapping at the root")

    required = ["pair", "exchange", "grid_levels", "lower_price", "upper_price", "amount_per_grid"]
    missing = [key for key in required if key not in parsed]
    if missing:
        raise ValueError(f"config missing: {', '.join(missing)}")

    lower = float(parsed["lower_price"])
    upper = float(parsed["upper_price"])
    if lower >= upper:
        raise ValueError("lower_price must be less than upper_price")
    levels = int(parsed["grid_levels"])
    if levels <= 0:
        raise ValueError("grid_levels must be a positive integer")

    parsed["lower_price"] = lower
    parsed["upper_price"] = upper
    parsed["grid_levels"] = levels
    parsed["amount_per_grid"] = float(parsed["amount_per_grid"])
    parsed["grid_type"] = str(parsed.get("grid_type", "arithmetic")).lower()
    if parsed["grid_type"] not in ("arithmetic", "geometric"):
        raise ValueError("grid_type must be 'arithmetic' or 'geometric'")
    parsed.setdefault("testnet", False)
    return parsed


def create_exchange(config: Dict[str, Any]) -> ccxt.Exchange:
    """Instantiate a ccxt exchange client, enabling sandbox mode when requested."""
    exchange_id = config["exchange"]
    if exchange_id not in ccxt.exchanges:
        raise ValueError(f"{exchange_id} is not a ccxt-supported exchange")

    params = {"enableRateLimit": True}
    exchange_cls = getattr(ccxt, exchange_id)
    exchange = exchange_cls(params)

    if config.get("testnet") and getattr(exchange, "set_sandbox_mode", None):
        exchange.set_sandbox_mode(True)

    return exchange


def main() -> None:
    config = load_config()
    exchange = create_exchange(config)

    print("Configuration loaded:")
    print(f"- pair: {config['pair']}")
    print(f"- grid_levels: {config['grid_levels']}")
    print(f"- lower_price: {config['lower_price']}")
    print(f"- upper_price: {config['upper_price']}")
    print(f"- sandbox: {config.get('testnet')}")

    try:
        exchange.load_markets()
        print("Connected to exchange; markets loaded.")
    except Exception as exc:  # pragma: no cover
        print(f"Warning: failed to load markets ({exc})")


if __name__ == "__main__":
    main()
