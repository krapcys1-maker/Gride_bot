import sys
from pathlib import Path

import ccxt
import yaml
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent
if not (ROOT_DIR / "config.yaml").exists():
    ROOT_DIR = ROOT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

CONFIG_FILE = ROOT_DIR / "config.yaml"


def load_config(path: Path = CONFIG_FILE) -> dict:
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("config.yaml must be a mapping")
    required = {"symbol", "lower_price", "upper_price"}
    missing = required.difference(data)
    if missing:
        raise ValueError(f"config.yaml missing keys: {', '.join(missing)}")
    return data


def init_exchange() -> ccxt.Exchange:
    load_dotenv()
    return ccxt.kucoin({"enableRateLimit": True})


def main() -> None:
    config = load_config()
    symbol = config["symbol"]
    lower = float(config["lower_price"])
    upper = float(config["upper_price"])
    if lower >= upper:
        raise ValueError("lower_price must be less than upper_price")

    exchange = init_exchange()
    ticker = exchange.fetch_ticker(symbol)
    price = ticker.get("last") or ticker.get("close")
    if price is None:
        raise RuntimeError("Unable to fetch current price")

    position = (price - lower) / (upper - lower)
    position_pct = position * 100

    print(f"Aktualna cena: {price}")
    print(f"Zakres siatki: {lower} - {upper}")
    print(f"Pozycja w siatce: {position_pct:.2f}%")

    if price < lower or price > upper:
        print("BŁĄD KRYTYCZNY: Cena poza siatką. Bot nie zadziała.")
        return

    if position_pct < 20 or position_pct > 80:
        print("UWAGA: Cena blisko krawędzi! Przesuń zakres, żeby bot miał miejsce do pracy.")


if __name__ == "__main__":
    main()
