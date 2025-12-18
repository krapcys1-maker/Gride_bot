import os
from collections import deque
from datetime import datetime
from typing import Deque, Dict, List, Tuple

import ccxt
import yaml
from dotenv import load_dotenv

from grid_logic import GridCalculator


CONFIG_FILE = "config.yaml"


def load_config(path: str = CONFIG_FILE) -> Dict[str, object]:
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("config.yaml must map keys to values")
    required = {"symbol", "lower_price", "upper_price", "grid_levels", "order_size"}
    missing = required.difference(data)
    if missing:
        raise ValueError(f"config.yaml missing values: {', '.join(missing)}")
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


def build_initial_orders(
    symbol: str, levels: List[float], price: float
) -> List[Dict[str, object]]:
    orders: List[Dict[str, object]] = []
    for level in levels:
        if level == price:
            continue
        side = "buy" if level < price else "sell"
        orders.append(
            {
                "symbol": symbol,
                "side": side,
                "price": level,
            }
        )
    return orders


def match_order(
    side: str,
    price: float,
    order_size: float,
    buy_queue: Deque[Tuple[float, float]],
    sell_queue: Deque[Tuple[float, float]],
) -> Tuple[float, float]:
    """Return realized profit and fees for a trade fill."""
    profit = 0.0
    filled_amount = order_size
    if side == "buy":
        if sell_queue:
            sell_price, sell_amount = sell_queue[0]
            matched = min(sell_amount, filled_amount)
            profit += (sell_price - price) * matched
            filled_amount -= matched
            sell_queue[0] = (sell_price, sell_amount - matched)
            if sell_queue[0][1] == 0:
                sell_queue.popleft()
        if filled_amount > 0:
            buy_queue.append((price, filled_amount))
    else:
        if buy_queue:
            buy_price, buy_amount = buy_queue[0]
            matched = min(buy_amount, filled_amount)
            profit += (price - buy_price) * matched
            filled_amount -= matched
            buy_queue[0] = (buy_price, buy_amount - matched)
            if buy_queue[0][1] == 0:
                buy_queue.popleft()
        if filled_amount > 0:
            sell_queue.append((price, filled_amount))
    fee = price * order_size * 0.001
    return profit, fee


def run_backtest() -> None:
    config = load_config()
    exchange = init_exchange()
    symbol = config["symbol"]
    order_size = float(config["order_size"])
    grid_levels = int(config["grid_levels"])
    lower_price = float(config["lower_price"])
    upper_price = float(config["upper_price"])

    ohlcv = exchange.fetch_ohlcv(symbol, timeframe="1h", limit=1000)
    if not ohlcv:
        raise RuntimeError("No historical data retrieved")

    timestamp = ohlcv[0][0]
    start_time = datetime.utcfromtimestamp(timestamp / 1000)
    start_price = float(ohlcv[0][1])
    calculator = GridCalculator(
        lower_price=lower_price, upper_price=upper_price, grid_levels=grid_levels
    )
    levels = calculator.calculate_levels()
    orders = build_initial_orders(symbol, levels, start_price)
    grid_step = round(levels[1] - levels[0], 10) if len(levels) > 1 else 0.0

    buy_queue: Deque[Tuple[float, float]] = deque()
    sell_queue: Deque[Tuple[float, float]] = deque()
    grid_profit = 0.0
    fees = 0.0
    transactions = 0

    for candle in ohlcv:
        _ts, _open, high, low, close, _volume = candle
        for order in orders[:]:
            level = float(order["price"])
            side = order["side"]
            filled = (side == "buy" and low <= level) or (side == "sell" and high >= level)
            if not filled:
                continue
            profit, fee = match_order(side, level, order_size, buy_queue, sell_queue)
            grid_profit += profit
            fees += fee
            transactions += 1
            orders.remove(order)
            new_price = round(level + grid_step, 10) if side == "buy" else round(level - grid_step, 10)
            new_side = "sell" if side == "buy" else "buy"
            orders.append(
                {"symbol": symbol, "side": new_side, "price": new_price}
            )

    final_price = float(ohlcv[-1][4])
    unrealized = sum((final_price - price) * amount for price, amount in buy_queue)
    unrealized += sum((price - final_price) * amount for price, amount in sell_queue)
    end_time = datetime.utcfromtimestamp(ohlcv[-1][0] / 1000)
    net_profit = grid_profit - fees

    print(f"Backtest period: {start_time} - {end_time}")
    print(f"Transactions executed: {transactions}")
    print(f"Grid Profit (realized): {grid_profit:.4f} USDT")
    print(f"Fees paid: {fees:.4f} USDT")
    print(f"Net Profit: {net_profit:.4f} USDT")
    print(f"Unrealized PnL: {unrealized:.4f} USDT")
    hold_profit = (final_price - start_price) * order_size
    print(f"Buy & Hold: {hold_profit:.4f} USDT")


if __name__ == "__main__":
    run_backtest()
