import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt


ROOT_DIR = Path(__file__).resolve().parent
if not (ROOT_DIR / "config.yaml").exists():
    ROOT_DIR = ROOT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

HISTORY_FILE = ROOT_DIR / "trade_history.csv"
CONFIG_FILE = ROOT_DIR / "config.yaml"


def load_config_symbol() -> str:
    if not CONFIG_FILE.exists():
        return "BTC/USDT"
    import yaml

    with open(CONFIG_FILE, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if isinstance(data, dict) and "symbol" in data:
        return data["symbol"]
    return "BTC/USDT"


def fetch_live_price(symbol: str) -> float | None:
    try:
        exchange = ccxt.kucoin({"enableRateLimit": True})
        ticker = exchange.fetch_ticker(symbol)
        return ticker.get("last") or ticker.get("close")
    except Exception:
        return None


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def load_trades() -> list[dict]:
    trades = []
    if not HISTORY_FILE.exists():
        return trades
    with open(HISTORY_FILE, encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            trades.append(row)
    return trades


def summarize(trades: list[dict]) -> dict:
    if not trades:
        return {}
    fees = 0.0
    cashflow = 0.0
    first_ts = None
    for row in trades:
        try:
            fee = float(row.get("fee_estimated", 0.0))
            price = float(row.get("price", 0.0))
            amount = float(row.get("amount", 0.0))
            side = str(row.get("side", "")).lower()
        except (TypeError, ValueError):
            continue
        fees += fee
        value = price * amount
        if side == "sell":
            cashflow += value
        else:
            cashflow -= value
        if first_ts is None:
            ts_str = row.get("timestamp")
            try:
                first_ts = datetime.fromisoformat(ts_str)
            except Exception:
                try:
                    first_ts = datetime.fromtimestamp(float(ts_str), tz=timezone.utc)
                except Exception:
                    first_ts = datetime.now(timezone.utc)
    profit = cashflow - fees
    last_trade_price = float(trades[-1].get("price", 0.0))
    return {
        "profit": profit,
        "fees": fees,
        "count": len(trades),
        "first_ts": first_ts,
        "last_price": last_trade_price,
    }


def main() -> None:
    symbol = load_config_symbol()
    while True:
        trades = load_trades()
        clear_screen()
        if not trades:
            print("Oczekiwanie na pierwszą transakcję bota...")
            time.sleep(5)
            continue

        summary = summarize(trades)
        now = datetime.now(timezone.utc)
        runtime = ""
        if summary["first_ts"]:
            delta = now - summary["first_ts"]
            runtime = str(delta).split(".")[0]

        live_price = fetch_live_price(symbol)
        last_price = summary["last_price"] if summary["last_price"] else live_price

        print("=" * 60)
        print(f" PAPER GRID DASHBOARD ({symbol}) ".center(60, "="))
        print("=" * 60)
        print(f"Czas działania : {runtime or 'n/a'}")
        print(f"Liczba transakcji : {summary['count']}")
        print(f"Ostatnia cena (trade) : {summary['last_price']:.2f}")
        if live_price:
            print(f"Ostatnia cena (live)  : {live_price:.2f}")
        print("-" * 60)
        print(f"Zrealizowany Profit : {summary['profit']:.6f} USDT")
        print(f"Szacowane Prowizje : {summary['fees']:.6f} USDT")
        if last_price:
            print(f"Referencyjna cena : {last_price:.2f}")
        print("=" * 60)
        time.sleep(5)


if __name__ == "__main__":
    main()
