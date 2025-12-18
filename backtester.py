"""
Backtester strategii Grid na danych 1m z KuCoin zapisanych w CSV.

- Szuka pliku CSV w katalogu data/ (timestamp, datetime, open, high, low, close, volume)
- Ładuje config.yaml (lower_price, upper_price, grid_levels, order_size)
- Symuluje siatkę z prowizją 0.1%, loguje postęp i raportuje wynik wraz z porównaniem z rynkiem (Buy & Hold).
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yaml

from grid_logic import GridCalculator


CONFIG_FILE = Path("config.yaml")
DATA_DIR = Path("data")
FEE_RATE = 0.001  # 0.1%
MAX_TRADES_PER_CANDLE = 20
PROGRESS_EVERY = 5000


@dataclass
class Order:
    price: float
    side: str  # "buy" lub "sell"
    amount: float


def find_csv_file(data_dir: Path = DATA_DIR) -> Path:
    if not data_dir.exists():
        raise FileNotFoundError(f"Brak katalogu z danymi: {data_dir}")
    preferred = sorted(data_dir.glob("*1m*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    candidates = preferred or sorted(data_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"Nie znaleziono pliku CSV w {data_dir}")
    return candidates[0]


def load_config(path: Path = CONFIG_FILE) -> Dict[str, float]:
    with path.open(encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    required = {"lower_price", "upper_price", "grid_levels", "order_size"}
    missing = required.difference(cfg)
    if missing:
        raise ValueError(f"config.yaml missing required keys: {', '.join(sorted(missing))}")
    return {
        "lower_price": float(cfg["lower_price"]),
        "upper_price": float(cfg["upper_price"]),
        "grid_levels": int(cfg["grid_levels"]),
        "order_size": float(cfg["order_size"]),
        "stop_loss_enabled": bool(cfg.get("stop_loss_enabled", True)),
        "grid_type": str(cfg.get("grid_type", "arithmetic")).lower(),
    }


def load_data(path: Optional[Path] = None) -> pd.DataFrame:
    csv_path = path or find_csv_file()
    print(f"Wczytuję dane z pliku: {csv_path}")
    df = pd.read_csv(csv_path)
    expected_cols = {"timestamp", "open", "high", "low", "close", "volume"}
    if not expected_cols.issubset(df.columns):
        raise ValueError(f"CSV musi zawierać kolumny: {', '.join(sorted(expected_cols))}")
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def initialize_orders(calculator: GridCalculator, start_price: float, order_size: float) -> List[Order]:
    orders: List[Order] = []
    for level in calculator.calculate_levels():
        if level == start_price:
            continue
        side = "buy" if level < start_price else "sell"
        orders.append(Order(price=level, side=side, amount=order_size))
    return orders


def initial_capital(orders: List[Order], start_price: float) -> Tuple[float, float, float]:
    """Oblicz wymagany kapitał: quote (USDT) + base (BTC) oraz łączną wartość w USDT."""
    quote_needed = sum(o.price * o.amount for o in orders if o.side == "buy")
    base_needed = sum(o.amount for o in orders if o.side == "sell")
    total_usdt = quote_needed + base_needed * start_price
    return quote_needed, base_needed, total_usdt


def backtest(df: pd.DataFrame, cfg: Dict[str, float]) -> None:
    calculator = GridCalculator(
        lower_price=cfg["lower_price"],
        upper_price=cfg["upper_price"],
        grid_levels=cfg["grid_levels"],
        grid_type=cfg["grid_type"],
    )
    grid_step = calculator.step
    grid_ratio = calculator.ratio
    start_price = float(df.iloc[0]["open"])
    if not (calculator.lower_price <= start_price <= calculator.upper_price):
        print(
            f"[WARN] Cena startowa {start_price} jest poza zakresem siatki "
            f"{calculator.lower_price}-{calculator.upper_price}"
        )
    orders = initialize_orders(calculator, start_price, cfg["order_size"])

    quote_balance, base_balance, initial_equity = initial_capital(orders, start_price)
    fees_paid = 0.0
    volume = 0.0
    trades = 0
    stop_trigger: Optional[pd.Timestamp] = None

    total_candles = len(df)
    for idx, row in df.iterrows():
        low = float(row["low"])
        high = float(row["high"])
        close = float(row["close"])
        if low < calculator.lower_price and cfg.get("stop_loss_enabled", True):
            sell_price = calculator.lower_price
            proceeds = sell_price * base_balance
            fee = proceeds * FEE_RATE
            quote_balance += proceeds - fee
            fees_paid += fee
            volume += proceeds
            trades += 1 if base_balance > 0 else 0
            base_balance = 0.0
            stop_trigger = row["timestamp"]
            print(f"[ALARM] Stop Loss aktywowany {stop_trigger} przy cenie {sell_price}. Koniec testu.")
            break
        trades_this_candle = 0
        while True:
            filled = False
            for order in list(orders):
                price = order.price
                if order.side == "buy" and low <= price:
                    cost = price * order.amount
                    fee = cost * FEE_RATE
                    quote_balance -= cost + fee
                    base_balance += order.amount
                    fees_paid += fee
                    volume += cost
                    trades += 1
                    trades_this_candle += 1
                    orders.remove(order)
                    if grid_ratio:
                        next_price = round(price * grid_ratio, 10)
                    else:
                        next_price = round(price + (grid_step or 0), 10)
                    orders.append(Order(price=next_price, side="sell", amount=order.amount))
                    filled = True
                    break
                if order.side == "sell" and high >= price:
                    proceeds = price * order.amount
                    fee = proceeds * FEE_RATE
                    quote_balance += proceeds - fee
                    base_balance -= order.amount
                    fees_paid += fee
                    volume += proceeds
                    trades += 1
                    trades_this_candle += 1
                    orders.remove(order)
                    if grid_ratio:
                        next_price = round(price / grid_ratio, 10)
                    else:
                        next_price = round(price - (grid_step or 0), 10)
                    orders.append(Order(price=next_price, side="buy", amount=order.amount))
                    filled = True
                    break
            if trades_this_candle >= MAX_TRADES_PER_CANDLE:
                print(
                    f"[WARN] Limit {MAX_TRADES_PER_CANDLE} transakcji na świeczkę osiągnięty "
                    f"({row['timestamp']}). Przechodzę dalej."
                )
                break
            if not filled:
                break

        if idx and idx % PROGRESS_EVERY == 0:
            print(f"Przetworzono {idx} / {total_candles} świeczek...")

    end_price = float(df.iloc[-1]["close"]) if stop_trigger is None else calculator.lower_price
    final_equity = quote_balance + base_balance * end_price
    pnl = final_equity - initial_equity
    roi_pct = (pnl / initial_equity) * 100 if initial_equity else 0.0

    market_start = float(df.iloc[0]["open"])
    market_end = end_price
    market_change_pct = ((market_end - market_start) / market_start) * 100 if market_start else 0.0
    buy_hold_value = initial_equity / market_start * market_end if market_start else 0.0
    bot_beats_market = "Tak" if final_equity > buy_hold_value else "Nie"

    start_date = df.iloc[0]["timestamp"]
    end_date = df.iloc[-1]["timestamp"]

    print("\n===== GRID BACKTEST REPORT =====")
    print(f"Okres testu        : {start_date} -> {end_date}")
    print(f"Liczba transakcji  : {trades}")
    print(f"Obrót (USDT)       : {volume:,.2f}")
    print(f"Prowizje (USDT)    : {fees_paid:,.2f}")
    print(f"Zysk netto (USDT)  : {pnl:,.2f}")
    print(f"ROI %              : {roi_pct:.2f}%")
    if stop_trigger:
        print(f"Test przerwany przez Stop Loss dnia {stop_trigger}")
        print("================================\n")
        return
    print("\n--- RYNEK vs BOT ---")
    print(f"Cena Start / Stop  : {market_start} -> {market_end}")
    print(f"Zmiana ceny rynku  : {market_change_pct:.2f}%")
    print(f"Buy & Hold (USDT)  : {buy_hold_value:,.2f}")
    print(f"Bot pobił rynek?   : {bot_beats_market}")
    print("================================\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest strategii Grid.")
    parser.add_argument("--file", help="Ścieżka do pliku CSV z danymi 1m")
    args = parser.parse_args()

    cfg = load_config()
    csv_path = Path(args.file) if args.file else None
    data = load_data(csv_path)
    backtest(data, cfg)


if __name__ == "__main__":
    main()
