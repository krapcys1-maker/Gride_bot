"""
Pobieranie historycznych świeczek OHLCV z KuCoin (public API, ccxt) z paginacją.

- Obsługa przedziału dat --start / --end (YYYY-MM-DD)
- Domyślnie 60 dni 1m dla BTC/USDT, gdy brak dat
- Plik wynikowy zawiera daty w nazwie
- Nagłówki: timestamp, datetime, open, high, low, close, volume.
"""

import argparse
import csv
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import ccxt


DEFAULT_SYMBOL = "BTC/USDT"
DEFAULT_TIMEFRAME = "1m"
DEFAULT_DAYS_BACK = 60
DATA_DIR = Path("data")


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def build_filename(symbol: str, timeframe: str, start: Optional[str], end: Optional[str]) -> Path:
    safe_symbol = symbol.replace("/", "-")
    if start and end:
        return DATA_DIR / f"kucoin_{safe_symbol}_{timeframe}_{start}_{end}.csv"
    return DATA_DIR / f"kucoin_{safe_symbol}_{timeframe}.csv"


def download_data(
    symbol: str,
    timeframe: str = DEFAULT_TIMEFRAME,
    days_back: int = DEFAULT_DAYS_BACK,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Path:
    """
    Pobierz OHLCV z KuCoin z paginacją po 1000 świec i zapisz do CSV.
    Zwraca ścieżkę do pliku.
    """
    if timeframe != "1m":
        raise ValueError("Ten skrypt obsługuje tylko timeframe 1m.")
    if start_date and not end_date:
        raise ValueError("Podaj również --end gdy używasz --start.")
    if end_date and not start_date:
        raise ValueError("Podaj również --start gdy używasz --end.")
    if not start_date and days_back <= 0:
        raise ValueError("days_back musi być dodatnie.")

    exchange = ccxt.kucoin({"enableRateLimit": True})
    tf_ms = exchange.parse_timeframe(timeframe) * 1000
    if start_date and end_date:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
        since = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)
        if since >= end_ms:
            raise ValueError("Data start musi być wcześniejsza niż end.")
        print(f"Pobieram dane {symbol} {timeframe} od {start_date} do {end_date}...")
    else:
        since = int((datetime.utcnow() - timedelta(days=days_back)).timestamp() * 1000)
        end_ms = exchange.milliseconds()
        print(f"Start pobierania {symbol} {timeframe} za ostatnie {days_back} dni...")

    ensure_data_dir()
    outfile = build_filename(symbol, timeframe, start_date, end_date)

    rows: List[List] = []

    while since < end_ms:
        try:
            batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
        except ccxt.NetworkError as exc:
            print(f"[WARN] Błąd sieci ({exc}), ponawiam za 1s...")
            time.sleep(1)
            continue
        except Exception as exc:  # pragma: no cover
            print(f"[ERROR] Nie udało się pobrać danych: {exc}")
            break

        if not batch:
            print("[INFO] Brak kolejnych danych, kończę.")
            break

        capped = [candle for candle in batch if candle[0] <= end_ms]
        rows.extend(capped)
        since = batch[-1][0] + tf_ms
        last_dt = datetime.utcfromtimestamp(batch[-1][0] / 1000).isoformat()
        print(f"Pobrano partię do {last_dt}, łączny rozmiar: {len(rows)}")

        time.sleep(0.5)  # ochrona przed rate limit

        if batch[-1][0] >= end_ms:
            break

    with outfile.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "datetime", "open", "high", "low", "close", "volume"])
        for ts, o, h, l, c, v in rows:
            writer.writerow([ts, datetime.utcfromtimestamp(ts / 1000).isoformat(), o, h, l, c, v])

    print(f"Zapisano {len(rows)} wierszy do {outfile}")
    return outfile


def main() -> None:
    parser = argparse.ArgumentParser(description="Pobierz historyczne OHLCV z KuCoin (1m).")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="Para handlowa, np. BTC/USDT")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS_BACK, help="Ile dni wstecz pobrać (domyślnie 60)")
    parser.add_argument("--start", help="Data start (YYYY-MM-DD)")
    parser.add_argument("--end", help="Data końcowa (YYYY-MM-DD)")
    args = parser.parse_args()

    download_data(
        args.symbol,
        DEFAULT_TIMEFRAME,
        days_back=args.days,
        start_date=args.start,
        end_date=args.end,
    )


if __name__ == "__main__":
    main()
