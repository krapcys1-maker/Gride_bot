import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import yaml


ROOT_DIR = Path(__file__).resolve().parent
if not (ROOT_DIR / "config.yaml").exists():
    ROOT_DIR = ROOT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
CONFIG_FILE = ROOT_DIR / "config.yaml"
DATA_DIR = ROOT_DIR / "data"

from grid_logic import GridCalculator


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
    required_cols = {"timestamp", "open", "high", "low", "close"}
    missing = required_cols.difference(df.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {', '.join(missing)}")
    df.sort_values("timestamp", inplace=True)
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


def simulate_grid(df: pd.DataFrame, grid_levels: int, config: Dict[str, object], start_capital: float = 1000.0):
    symbol = config["symbol"]
    order_size = float(config["order_size"])
    lower_price = float(config["lower_price"])
    upper_price = float(config["upper_price"])
    fee_rate = 0.001

    start_price = float(df.iloc[0]["open"])
    end_price = float(df.iloc[-1]["close"])

    calculator = GridCalculator(lower_price, upper_price, grid_levels)
    levels = calculator.calculate_levels()
    grid_step = levels[1] - levels[0] if len(levels) > 1 else 0.0
    orders = build_initial_orders(symbol, levels, start_price)

    balance_usdt = start_capital
    balance_coin = 0.0
    grid_profit = 0.0
    fees_paid = 0.0
    trades = 0

    for _, row in df.iterrows():
        low = float(row["low"])
        high = float(row["high"])
        for order in orders[:]:
            level = float(order["price"])
            side = order["side"]
            filled = (side == "buy" and low <= level) or (side == "sell" and high >= level)
            if not filled:
                continue

            value = level * order_size
            fee = value * fee_rate
            fees_paid += fee
            trades += 1

            if side == "buy":
                balance_usdt -= value
                balance_coin += order_size
                balance_usdt -= fee
                grid_profit -= value
            else:
                balance_usdt += value
                balance_coin -= order_size
                balance_usdt -= fee
                grid_profit += value

            opposite_side, new_price = rotate_order(side, level, grid_step)
            orders.remove(order)
            orders.append({"symbol": symbol, "side": opposite_side, "price": new_price})

    end_value = balance_usdt + balance_coin * end_price
    net_profit = end_value - start_capital
    profit_fee_ratio = grid_profit / fees_paid if fees_paid else float("inf")
    grid_yield_pct = (net_profit / start_capital) * 100
    return {
        "grid_levels": grid_levels,
        "grid_profit": grid_profit,
        "fees_paid": fees_paid,
        "net_profit": net_profit,
        "grid_yield_pct": grid_yield_pct,
        "profit_fee_ratio": profit_fee_ratio,
        "trades": trades,
        "end_value": end_value,
        "start_price": start_price,
        "end_price": end_price,
    }


def main() -> None:
    config = load_config()
    symbol = config["symbol"]
    df = load_history_csv(symbol)

    split_idx = int(len(df) * 0.7)
    df_train = df.iloc[:split_idx].copy()
    df_val = df.iloc[split_idx:].copy()

    # Run optimization on validation set only to avoid overfitting to train.
    results = []
    for levels in range(10, 150, 5):
        result = simulate_grid(df_val, levels, config)
        results.append(result)

    if not results:
        print("No configurations evaluated.")
        return

    results.sort(key=lambda r: r["net_profit"], reverse=True)
    top = results[:10]

    val_start_price = float(df_val.iloc[0]["open"])
    val_end_price = float(df_val.iloc[-1]["close"])
    start_capital = 1000.0
    buy_hold_profit = (val_end_price - val_start_price) * (start_capital / val_start_price)

    print(f"Validation set length: {len(df_val)} candles")
    print("Top 10 configurations (by validation net profit):")
    print(f"{'Levels':>8} | {'Net Profit':>12} | {'P/F Ratio':>10} | {'Trades':>8} | {'Avg Profit/Grid':>16}")
    print("-" * 64)
    for r in top:
        warning = " (Ryzowne!)" if r["profit_fee_ratio"] < 5 else ""
        avg_profit = r["net_profit"] / r["grid_levels"] if r["grid_levels"] else 0.0
        print(
            f"{r['grid_levels']:>8} | "
            f"{r['net_profit']:>12.4f} | "
            f"{r['profit_fee_ratio']:>10.2f} | "
            f"{r['trades']:>8} | "
            f"{avg_profit:>16.4f}"
            f"{warning}"
        )

    best = top[0]
    print("\nComparison vs Buy & Hold on validation:")
    print(f"- Buy & Hold profit: {buy_hold_profit:.4f} USDT")
    print(f"- Best grid (levels={best['grid_levels']}): net {best['net_profit']:.4f} USDT")
    print(
        f"- Profit/Fee ratio: {best['profit_fee_ratio']:.2f}, "
        f"Grid yield: {best['grid_yield_pct']:.2f}%"
    )


if __name__ == "__main__":
    main()
