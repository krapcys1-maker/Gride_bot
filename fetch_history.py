import csv
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import yaml
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent
if not (ROOT_DIR / "config.yaml").exists():
    ROOT_DIR = ROOT_DIR.parent
CONFIG_FILE = ROOT_DIR / "config.yaml"


def load_config(path: Path = CONFIG_FILE) -> dict[str, object]:
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("config.yaml must map keys to values")
    if "symbol" not in data:
        raise ValueError("config.yaml must define a symbol")
    return data


def init_exchange() -> ccxt.Exchange:
    load_dotenv()
    api_key = os.getenv("KUCOIN_API_KEY")
    api_secret = os.getenv("KUCOIN_API_SECRET")
    passphrase = os.getenv("KUCOIN_PASSPHRASE")
    credentials = {}
    if api_key and api_secret and passphrase:
        credentials = {
            "apiKey": api_key,
            "secret": api_secret,
            "password": passphrase,
        }
    return ccxt.kucoin({**credentials, "enableRateLimit": True})


def fetch_history() -> None:
    config = load_config()
    symbol = config["symbol"]
    timeframe = "5m"
    start_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime.now(timezone.utc)
    since = int(start_dt.timestamp() * 1000)
    end_ts = int(end_dt.timestamp() * 1000)
    timeframe_ms = 5 * 60 * 1000

    exchange = init_exchange()
    output_dir = ROOT_DIR / "data"
    output_dir.mkdir(exist_ok=True)
    sanitized_symbol = symbol.replace("/", "-")
    filename = output_dir / f"kucoin_{sanitized_symbol}_{timeframe}_2024.csv"

    with open(filename, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "datetime", "open", "high", "low", "close", "volume"])

        while since < end_ts:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
            if not ohlcv:
                break
            start_ts, *_ = ohlcv[0]
            end_ts_batch = ohlcv[-1][0]
            start_str = datetime.fromtimestamp(start_ts / 1000, timezone.utc).isoformat()
            end_str = datetime.fromtimestamp(end_ts_batch / 1000, timezone.utc).isoformat()
            print(f"Fetched {len(ohlcv)} candles {start_str} - {end_str}")

            for ts, open_, high, low, close, volume in ohlcv:
                writer.writerow(
                    [
                        ts,
                        datetime.fromtimestamp(ts / 1000, timezone.utc).isoformat(),
                        open_,
                        high,
                        low,
                        close,
                        volume,
                    ]
                )

            since = end_ts_batch + timeframe_ms
            time.sleep(0.3)


if __name__ == "__main__":
    fetch_history()
