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


def fetch_history(
    start: datetime | None = None,
    end: datetime | None = None,
    output_path: Path | None = None,
    timeframe: str = "1m",
) -> Path:
    config = load_config()
    symbol = config["symbol"]
    start_dt = start or datetime(2024, 1, 1, tzinfo=timezone.utc)
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    end_dt = end or datetime.now(timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)
    if start_dt >= end_dt:
        raise ValueError("Start date must be earlier than end date")
    since = int(start_dt.timestamp() * 1000)
    end_ts = int(end_dt.timestamp() * 1000)

    exchange = init_exchange()
    output_dir = ROOT_DIR / "data"
    output_dir.mkdir(exist_ok=True)
    sanitized_symbol = symbol.replace("/", "-")
    filename = output_path or output_dir / f"ohlc_{sanitized_symbol}_{timeframe}_from_kucoin.csv"
    timeframe_ms = exchange.parse_timeframe(timeframe) * 1000

    rows: list[list] = []

    while since < end_ts:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
        if not ohlcv:
            break
        start_ts_batch, *_ = ohlcv[0]
        end_ts_batch = ohlcv[-1][0]
        start_str = datetime.fromtimestamp(start_ts_batch / 1000, timezone.utc).isoformat()
        end_str = datetime.fromtimestamp(end_ts_batch / 1000, timezone.utc).isoformat()
        print(f"Fetched {len(ohlcv)} candles {start_str} - {end_str}")

        for ts, open_, high, low, close, volume in ohlcv:
            rows.append([ts, open_, high, low, close, volume])

        since = end_ts_batch + timeframe_ms
        time.sleep(0.3)

    # sort and deduplicate by ts
    rows_sorted = sorted(rows, key=lambda r: r[0])
    deduped = []
    seen = set()
    for r in rows_sorted:
        if r[0] in seen:
            continue
        seen.add(r[0])
        deduped.append(r)

    with open(filename, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ts", "datetime", "open", "high", "low", "close", "volume"])
        for ts, open_, high_, low_, close_, vol_ in deduped:
            writer.writerow([ts, datetime.fromtimestamp(ts / 1000, timezone.utc).isoformat(), open_, high_, low_, close_, vol_])

    print(f"Zapisano {len(deduped)} wierszy do {filename}")

    return filename


def _parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)


def main(argv=None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Fetch OHLC history from KuCoin and save as CSV.")
    parser.add_argument("--start", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", help="End date YYYY-MM-DD")
    parser.add_argument("--out", help="Output CSV path")
    parser.add_argument("--timeframe", default="1m", help="Timeframe (default: 1m)")
    args = parser.parse_args(argv)

    start_dt = _parse_date(args.start)
    end_dt = _parse_date(args.end)
    out_path = Path(args.out) if args.out else None

    fetch_history(start=start_dt, end=end_dt, output_path=out_path, timeframe=args.timeframe)


if __name__ == "__main__":
    main()
