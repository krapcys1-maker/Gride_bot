import math
import os
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import yaml

from grid_logic import GridCalculator


ROOT_DIR = Path(__file__).resolve().parent
if not (ROOT_DIR / "config.yaml").exists():
    ROOT_DIR = ROOT_DIR.parent
CONFIG_FILE = ROOT_DIR / "config.yaml"
DATA_DIR = ROOT_DIR / "data"


def load_config(path: Path = CONFIG_FILE) -> Dict[str, object]:
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("config.yaml must map keys to values")
    required = {"symbol", "lower_price", "upper_price", "grid_levels", "order_size"}
    missing = required.difference(data)
    if missing:
        raise ValueError(f"config.yaml missing values: {', '.join(missing)}")
    return data


def load_history_csv(symbol: str, timeframe: str = "5m") -> pd.DataFrame:
    sanitized = symbol.replace("/", "-")
    filename = DATA_DIR / f"kucoin_{sanitized}_{timeframe}_2024.csv"
    if not filename.exists():
        raise FileNotFoundError(f"History file not found: {filename}")
    df = pd.read_csv(filename)
    required_cols = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required_cols.difference(df.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {', '.join(missing)}")
    return df


def build_initial_orders(symbol: str, levels: List[float], start_price: float) -> List[Dict[str, object]]:
    orders: List[Dict[str, object]] = []
    for level in levels:
        if math.isclose(level, start_price):
            continue
        side = "buy" if level < start_price else "sell"
        orders.append({"symbol": symbol, "side": side, "price": level})
    return orders


def rotate_order(side: str, level: float, grid_step: float) -> Tuple[str, float]:
    if side == "buy":
        return "sell", round(level + grid_step, 10)
    return "buy", round(level - grid_step, 10)


def run_backtest(timeframe: str = "5m") -> None:
    config = load_config()
    symbol = config["symbol"]
    order_size = float(config["order_size"])
    grid_levels = int(config["grid_levels"])
    lower_price = float(config["lower_price"])
    upper_price = float(config["upper_price"])

    df = load_history_csv(symbol, timeframe)
    df.sort_values("timestamp", inplace=True)
    start_price = float(df.iloc[0]["open"])
    end_price = float(df.iloc[-1]["close"])

    calculator = GridCalculator(lower_price, upper_price, grid_levels)
    levels = calculator.calculate_levels()
    grid_step = levels[1] - levels[0] if len(levels) > 1 else 0.0
    orders = build_initial_orders(symbol, levels, start_price)

    balance_usdt = 1000.0
    balance_coin = 0.0
    fee_rate = 0.001
    grid_profit = 0.0
    fees_paid = 0.0
    trades: List[Dict[str, object]] = []

    for _, row in df.iterrows():
        low = float(row["low"])
        high = float(row["high"])
        ts = int(row["timestamp"])
        for order in orders[:]:
            level = float(order["price"])
            side = order["side"]
            filled = (side == "buy" and low <= level) or (side == "sell" and high >= level)
            if not filled:
                continue

            value = level * order_size
            fee = value * fee_rate
            fees_paid += fee

            if side == "buy":
                balance_usdt -= value
                balance_coin += order_size
            else:
                balance_usdt += value
                balance_coin -= order_size

            opposite_side, new_price = rotate_order(side, level, grid_step)
            orders.remove(order)
            orders.append({"symbol": symbol, "side": opposite_side, "price": new_price})

            trades.append(
                {
                    "timestamp": ts,
                    "side": side,
                    "price": level,
                    "amount": order_size,
                    "fee": fee,
                }
            )

            grid_profit += value if side == "sell" else -value

    end_portfolio_value = balance_usdt + balance_coin * end_price
    start_portfolio_value = 1000.0
    grid_net = grid_profit - fees_paid
    hold_profit = (end_price - start_price) * (start_portfolio_value / start_price)
    profit_to_fee_ratio = grid_profit / fees_paid if fees_paid else float("inf")

    print(f"Backtest on {symbol} ({timeframe}) candles: {len(df)}")
    print(f"Grid Profit (gross): {grid_profit:.4f} USDT")
    print(f"Fees paid: {fees_paid:.4f} USDT")
    print(f"Net Profit (grid - fees): {grid_net:.4f} USDT")
    print(f"End portfolio value: {end_portfolio_value:.4f} USDT (start 1000 USDT)")
    print(f"Unrealized PnL vs start: {end_portfolio_value - start_portfolio_value:.4f} USDT")
    print(f"Buy & Hold (start 1000 USDT): {hold_profit:.4f} USDT")
    print(f"Profit to Fee Ratio: {profit_to_fee_ratio:.4f}")


if __name__ == "__main__":
    run_backtest()
