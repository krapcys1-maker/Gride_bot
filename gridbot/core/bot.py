import math
import os
import random
import time
from itertools import cycle
from uuid import uuid4
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import ccxt

from grid_logic import GridCalculator

from .config import CONFIG_FILE, DB_FILE, DRY_RUN, load_config
from .exchange import init_exchange
from .storage import Storage


class GridBot:
    """Grid trading bot with SQLite persistence for orders and trade history."""

    def __init__(
        self,
        config_path: Path = CONFIG_FILE,
        db_path: Path = DB_FILE,
        dry_run: bool = DRY_RUN,
        offline: Optional[bool] = None,
        offline_scenario: Optional[str] = None,
        offline_once: bool = False,
        seed: Optional[int] = None,
    ) -> None:
        if config_path is None:
            config_path = CONFIG_FILE
        if db_path is None:
            db_path = DB_FILE
        if not isinstance(config_path, Path):
            config_path = Path(config_path)
        if not isinstance(db_path, Path):
            db_path = Path(db_path)
        if seed is not None:
            random.seed(seed)
        self.dry_run = dry_run
        self.config = load_config(config_path)
        offline_requested = (
            bool(offline)
            or str(os.getenv("GRIDBOT_OFFLINE", "")).lower() in {"1", "true", "yes"}
            or bool(self.config.get("offline"))
        )
        self.offline = offline_requested
        self.offline_once = offline_once
        self.offline_scenario = offline_scenario
        if self.offline:
            self.dry_run = True
        self.symbol = str(self.config["symbol"])
        self.order_size = float(self.config["order_size"])
        self.grid_levels = int(self.config["grid_levels"])
        self.lower_price = float(self.config["lower_price"])
        self.upper_price = float(self.config["upper_price"])
        self.grid_type = str(self.config.get("grid_type", "arithmetic"))
        self.trailing_up = bool(self.config["trailing_up"])
        self.stop_loss_enabled = bool(self.config["stop_loss_enabled"])
        self.status = "RUNNING"

        self._offline_price_cycle: Optional[Iterable[float]] = None
        self._offline_feed_exhausted = False
        if self.offline:
            self._prepare_offline_feed()

        self.exchange = init_exchange(offline=self.offline, price_provider=self._next_offline_price if self.offline else None)

        self.storage = Storage(db_path)
        self._init_db()

        self._load_bot_state()

        self.calculator = GridCalculator(
            lower_price=self.lower_price,
            upper_price=self.upper_price,
            grid_levels=self.grid_levels,
            grid_type=self.grid_type,
        )
        self.grid_step = self.calculator.step
        self.grid_ratio = self.calculator.ratio

    def reset_state(self) -> None:
        """Clear persisted state and revert prices to config defaults."""
        self.storage.reset_state()
        self.lower_price = float(self.config["lower_price"])
        self.upper_price = float(self.config["upper_price"])
        self.status = "RUNNING"
        self.calculator = GridCalculator(
            lower_price=self.lower_price,
            upper_price=self.upper_price,
            grid_levels=self.grid_levels,
            grid_type=self.grid_type,
        )
        self.grid_step = self.calculator.step
        self.grid_ratio = self.calculator.ratio

    def _init_db(self) -> None:
        self.storage._init_db()

    def _load_bot_state(self) -> None:
        state = self.storage.load_bot_state()
        if state:
            lower_price, upper_price, status = state
            self.lower_price = lower_price
            self.upper_price = upper_price
            self.status = status

    def _save_bot_state(self) -> None:
        self.storage.save_bot_state(self.lower_price, self.upper_price, self.status)

    def _load_offline_prices(self) -> List[float]:
        feed: List[float] = []
        config_prices = self.config.get("offline_prices")
        if isinstance(config_prices, list):
            for price in config_prices:
                try:
                    feed.append(float(price))
                except (TypeError, ValueError):
                    continue
        if feed:
            return feed

        csv_path = Path("data/offline_prices.csv")
        if csv_path.exists():
            import csv

            with csv_path.open(newline="", encoding="utf-8") as handle:
                reader = csv.reader(handle)
                for row in reader:
                    if not row:
                        continue
                    if len(row) == 1 and row[0].lower() == "price":
                        continue
                    candidates = [row[0]]
                    if len(row) > 1:
                        candidates.append(row[1])
                    parsed = None
                    for candidate in candidates:
                        try:
                            parsed = float(candidate)
                            break
                        except (TypeError, ValueError):
                            continue
                    if parsed is not None:
                        feed.append(parsed)
        return feed

    def _generate_offline_scenario(self, scenario: str, length: int = 500) -> List[float]:
        base = 88000.0
        prices: List[float] = []
        if scenario == "trend_up":
            for i in range(length):
                drift = i * 3
                noise = random.uniform(-50, 50)
                prices.append(base - 400 + drift + noise)
        elif scenario == "trend_down":
            for i in range(length):
                drift = i * -3
                noise = random.uniform(-50, 50)
                prices.append(base + 400 + drift + noise)
        elif scenario == "flash_crash":
            stable_len = max(50, length // 5)
            crash_len = max(20, length // 10)
            recover_len = length - stable_len - crash_len
            for i in range(stable_len):
                noise = random.uniform(-40, 40)
                prices.append(base + noise)
            crash_drop = random.uniform(0.15, 0.25)
            crash_price = base * (1 - crash_drop)
            for i in range(crash_len):
                noise = random.uniform(-30, 30)
                prices.append(crash_price + noise)
            for i in range(recover_len):
                frac = (i + 1) / recover_len
                target = crash_price + (base - crash_price) * 0.6
                noise = random.uniform(-50, 50)
                prices.append(crash_price + (target - crash_price) * frac + noise)
        else:  # range / default
            for i in range(length):
                wave = math.sin(i / 12) * 300
                noise = random.uniform(-80, 80)
                prices.append(base + wave + noise)
        return prices

    def _prepare_offline_feed(self) -> None:
        prices: List[float] = []
        if self.offline_scenario:
            prices = self._generate_offline_scenario(self.offline_scenario)
        if not prices:
            prices = self._load_offline_prices()
        self._offline_feed_warned = False
        if prices:
            if self.offline_once:
                self._offline_price_cycle = iter(prices)
                self._offline_feed_loop = False
            else:
                self._offline_price_cycle = cycle(prices)
                self._offline_feed_loop = True
        else:
            self._offline_price_cycle = None
            self._offline_feed_loop = False

    def _next_offline_price(self) -> Optional[float]:
        if not self._offline_price_cycle:
            if not getattr(self, "_offline_feed_warned", False):
                print("[WARN] Offline mode: no price feed available (offline_prices or data/offline_prices.csv).")
                self._offline_feed_warned = True
            self._offline_feed_exhausted = True
            return None
        try:
            return next(self._offline_price_cycle)
        except StopIteration:
            self._offline_feed_exhausted = True
            if not getattr(self, "_offline_feed_warned", False):
                print("[WARN] Offline mode: price feed exhausted.")
                self._offline_feed_warned = True
            return None

    def mark_stopped(self) -> None:
        """Persist STOPPED status."""
        self.status = "STOPPED"
        self._save_bot_state()

    def load_active_orders(self) -> List[Dict[str, Any]]:
        exchange_id = getattr(self.exchange, "id", "exchange")
        return self.storage.load_active_orders(self.order_size, exchange_id)

    def save_active_orders(self, orders: List[Dict[str, Any]]) -> None:
        self.storage.save_active_orders(orders)

    def log_trade(self, trade_data: Dict[str, Any]) -> None:
        self.storage.log_trade(trade_data)

    def create_limit_order(self, side: str, price: float, amount: float) -> Optional[Dict[str, Any]]:
        """Place a limit order (real or simulated) and return stored representation."""
        now_ts = datetime.utcnow().isoformat()
        exchange_id = getattr(self.exchange, "id", "exchange")

        if self.dry_run:
            # unikalne id potrzebne, bo active_orders.id jest PRIMARY KEY w SQLite
            order_id = f"sim_{side}_{self.symbol}_{uuid4().hex}"
            print(f"[DRY RUN] plan zlecenia {side} {amount} {self.symbol} po cenie {price}")
            return {
                "id": order_id,
                "symbol": self.symbol,
                "side": side,
                "price": price,
                "amount": amount,
                "exchange": exchange_id,
                "status": "open",
                "timestamp": now_ts,
            }

        attempts = 0
        while attempts < 2:
            try:
                order = self.exchange.create_order(self.symbol, "limit", side, amount, price)
                order_id = order.get("id") or order.get("orderId")
                if not order_id:
                    print(f"[ERROR] Brak ID zlecenia dla {side} {amount}@{price}")
                    return None

                raw_ts = order.get("timestamp")
                order_timestamp: str
                if isinstance(raw_ts, (int, float)):
                    order_timestamp = datetime.utcfromtimestamp(raw_ts / 1000).isoformat()
                else:
                    order_timestamp = str(order.get("datetime") or now_ts)

                status = order.get("status") or "open"
                print(f"[LIVE] Zlozono zlecenie {order_id}: {side} {amount} {self.symbol} @ {price}")
                return {
                    "id": str(order_id),
                    "symbol": self.symbol,
                    "side": side,
                    "price": price,
                    "amount": amount,
                    "exchange": exchange_id,
                    "status": status,
                    "timestamp": order_timestamp,
                }
            except ccxt.InsufficientFunds as exc:
                print(f"[CRITICAL] Brak srodkow dla zlecenia {side} {amount}@{price}: {exc}")
                return None
            except ccxt.NetworkError as exc:
                attempts += 1
                print(f"[WARN] Problem sieci podczas skladania zlecenia {side} {amount}@{price}: {exc}")
                time.sleep(1)
                if attempts >= 2:
                    return None
            except Exception as exc:  # pragma: no cover
                print(f"[ERROR] Nie udalo sie zlozyc zlecenia {side} {amount}@{price}: {exc}")
                return None

        return None

    def place_initial_grid(self, current_price: float) -> List[Dict[str, Any]]:
        """Simulate placing the initial grid and return the order plan."""
        orders: List[Dict[str, Any]] = []
        for level in self.calculator.calculate_levels():
            if level == current_price:
                continue
            side = "buy" if level < current_price else "sell"
            created = self.create_limit_order(side, level, self.order_size)
            if created:
                orders.append(created)
        if orders:
            self.save_active_orders(orders)
            print(f"Siatka zainicjowana. Zapisano {len(orders)} zlecen")
        return orders

    def check_order_status(
        self,
        order: Dict[str, Any],
        current_price: Optional[float],
    ) -> Tuple[str, Optional[float], float]:
        """
        Determine the status of an order.

        Returns (status, fill_price, filled_amount).
        """
        side = order["side"].lower()
        if self.dry_run:
            if current_price is None:
                return "open", None, 0.0

            order_price = float(order["price"])
            filled = (side == "buy" and current_price <= order_price) or (
                side == "sell" and current_price >= order_price
            )
            if filled:
                return "closed", order_price, float(order.get("amount", self.order_size))
            return "open", None, 0.0

        try:
            order_info = self.exchange.fetch_order(order["id"], self.symbol)
        except ccxt.NetworkError as exc:
            print(f"[WARN] Problem sieci podczas pobierania statusu {order['id']}: {exc}")
            time.sleep(1)
            return "open", None, 0.0
        except Exception as exc:  # pragma: no cover
            print(f"[WARN] Nie udalo sie pobrac statusu zlecenia {order['id']}: {exc}")
            return "open", None, 0.0

        status = str(order_info.get("status") or "").lower()
        fill_price = order_info.get("average") or order_info.get("price")
        filled_amount = float(order_info.get("filled") or order_info.get("amount") or order.get("amount", self.order_size))
        try:
            fill_price = float(fill_price) if fill_price is not None else None
        except (TypeError, ValueError):
            fill_price = None

        return status, fill_price, filled_amount

    def check_trailing(self, current_price: Optional[float]) -> None:
        """Shift the grid upward during strong uptrend when enabled."""
        if not self.trailing_up or current_price is None:
            return

        if self.grid_ratio:
            trigger_price = self.upper_price * self.grid_ratio
        else:
            trigger_price = self.upper_price + (self.grid_step or 0)
        if current_price <= trigger_price:
            return

        if self.grid_ratio:
            new_lower = round(self.lower_price * self.grid_ratio, 10)
            new_upper = round(self.upper_price * self.grid_ratio, 10)
        else:
            new_lower = round(self.lower_price + (self.grid_step or 0), 10)
            new_upper = round(self.upper_price + (self.grid_step or 0), 10)

        orders = self.load_active_orders()
        lowest_buy: Optional[Dict[str, Any]] = None
        for order in orders:
            if order["side"].lower() != "buy":
                continue
            if lowest_buy is None or order["price"] < lowest_buy["price"]:
                lowest_buy = order

        if lowest_buy:
            cancelled = False
            if self.dry_run:
                cancelled = True
            else:
                try:
                    self.exchange.cancel_order(lowest_buy["id"], self.symbol)
                    cancelled = True
                except ccxt.NetworkError as exc:
                    print(f"[WARN] Problem sieci podczas anulowania {lowest_buy['id']}: {exc}")
                    time.sleep(1)
                except Exception as exc:  # pragma: no cover
                    print(f"[WARN] Nie udalo sie anulowac {lowest_buy['id']}: {exc}")
            if cancelled:
                try:
                    self.storage.delete_active_order(lowest_buy["id"])
                    orders = [o for o in orders if o["id"] != lowest_buy["id"]]
                except Exception as exc:  # pragma: no cover
                    print(f"[WARN] Nie udalo sie usunac dolnego zlecenia {lowest_buy['id']}: {exc}")
                    return
            else:
                return

        new_sell = self.create_limit_order("sell", new_upper, self.order_size)
        if new_sell:
            orders.append(new_sell)

        self.lower_price = new_lower
        self.upper_price = new_upper
        self.calculator = GridCalculator(
            lower_price=self.lower_price,
            upper_price=self.upper_price,
            grid_levels=self.grid_levels,
            grid_type=self.grid_type,
        )
        self.grid_step = self.calculator.step
        self.grid_ratio = self.calculator.ratio
        self._save_bot_state()
        self.save_active_orders(orders)
        print(f"[TRAILING] Przesunieto siatke w gore do zakresu {new_lower}-{new_upper}")

    def panic_sell(self, current_price: float) -> None:
        """Execute stop-loss: cancel orders, liquidate base, mark bot stopped."""
        print("[ALARM] Cena przebila dolny zakres! Wykonano Panic Sell. Kapital zabezpieczony w USDT.")
        active_orders = self.load_active_orders()
        if not self.dry_run:
            for order in active_orders:
                try:
                    self.exchange.cancel_order(order["id"], self.symbol)
                except Exception as exc:  # pragma: no cover
                    print(f"[WARN] Nie udalo sie anulowac zlecenia {order['id']}: {exc}")
        self.storage.clear_active_orders()

        base_currency = self.symbol.split("/")[0]
        if not self.dry_run:
            try:
                balance = self.exchange.fetch_balance()
                base_free = float(balance.get(base_currency, {}).get("free", 0) or 0)
            except Exception as exc:  # pragma: no cover
                base_free = 0.0
                print(f"[WARN] Nie udalo sie pobrac balansu do panic sell: {exc}")
            if base_free > 0:
                try:
                    self.exchange.create_order(self.symbol, "market", "sell", base_free)
                    print(f"[LIVE] Sprzedano {base_free} {base_currency} po cenie rynkowej")
                except Exception as exc:  # pragma: no cover
                    print(f"[WARN] Nie udalo sie zrealizowac panic sell: {exc}")

        self.status = "STOPPED"
        self._save_bot_state()

    def monitor_grid(
        self,
        current_price: float,
    ) -> List[Dict[str, Any]]:
        """Check real fills via exchange (or simulate in dry-run) and flip executed orders."""
        orders = self.load_active_orders()
        updated_orders = orders[:]
        modified = False

        for order in orders:
            status, fill_price, filled_amount = self.check_order_status(order, current_price)
            if status == "open":
                continue
            if status == "canceled":
                try:
                    self.storage.delete_active_order(order["id"])
                    updated_orders.remove(order)
                    modified = True
                except Exception as exc:  # pragma: no cover
                    print(f"[WARN] Nie udalo sie usunac anulowanego zlecenia {order['id']}: {exc}")
                continue
            if status != "closed":
                continue

            execution_price = fill_price if fill_price is not None else float(order["price"])
            trade_value = round(execution_price * filled_amount, 10)
            trade_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "symbol": self.symbol,
                "side": order["side"],
                "price": execution_price,
                "amount": filled_amount,
                "value": trade_value,
                "fee_estimated": round(trade_value * 0.001, 10),
            }
            self.log_trade(trade_data)

            opposite_side = "sell" if order["side"].lower() == "buy" else "buy"
            if self.grid_ratio:
                new_price = round(order["price"] * self.grid_ratio, 10) if order["side"].lower() == "buy" else round(
                    order["price"] / self.grid_ratio, 10
                )
            else:
                new_price = round(order["price"] + (self.grid_step or 0), 10) if order["side"].lower() == "buy" else round(
                    order["price"] - (self.grid_step or 0), 10
                )

            new_order = self.create_limit_order(opposite_side, new_price, self.order_size)

            try:
                self.storage.replace_active_order(order["id"], new_order)
                updated_orders.remove(order)
                if new_order:
                    updated_orders.append(new_order)
                modified = True
            except Exception as exc:  # pragma: no cover
                print(f"[WARN] Blad podczas aktualizacji bazy dla zlecenia {order['id']}: {exc}")

        if modified:
            self.save_active_orders(updated_orders)

        return updated_orders

    def fetch_current_price(self) -> Optional[float]:
        """Fetch latest price for configured symbol."""
        if self.offline:
            price = self._next_offline_price()
            if price is None and self.offline_once:
                print("[INFO] Offline feed finished; stopping bot.")
            return price
        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            return ticker.get("last") or ticker.get("close")
        except Exception as exc:  # pragma: no cover
            print(f"Blad podczas pobierania tickera: {exc}")
            return None

    def risk_check(self, current_price: Optional[float]) -> None:
        """Warn the operator when potential profit per grid is below exchange fees."""
        if current_price is None:
            return

        if self.grid_ratio:
            profit_percent = (self.grid_ratio - 1)
            print(f"[INFO] Siatka (geometric): krok ~{profit_percent*100:.4f}%")
        else:
            grid_range = float(self.upper_price) - float(self.lower_price)
            profit_percent = (grid_range / self.grid_levels) / current_price
            print(f"[INFO] Siatka: skok co {grid_range / self.grid_levels:.2f} (~{profit_percent*100:.4f}%)")
        if profit_percent < 0.002:
            print("\n" + "!" * 50)
            print(
                f"CRITICAL WARNING: zysk na kratce to tylko {profit_percent*100:.4f}%!"
            )
            print("Gielda pobiera ok. 0.1% - 0.2% prowizji (entry + exit).")
            print("Sugerowane: zmniejsz liczbe grid_levels lub zwieksz zakres.")
            print("!" * 50 + "\n")
            time.sleep(5)

    def run(self, interval: float = 10.0, max_steps: Optional[int] = None) -> None:
        """Start the bot loop: load state, fetch price, and monitor the grid."""
        if self.dry_run:
            print("Dry-run mode: skipping balance check.")
        else:
            try:
                balance = self.exchange.fetch_balance()
                print("Balance fetched, exchange keys look valid.")
            except Exception as exc:  # pragma: no cover
                print(f"Unable to fetch balance: {exc}")

        initial_price = self.fetch_current_price()
        self.risk_check(initial_price)

        active_orders = self.load_active_orders()
        if active_orders:
            print(f"Zaladowano {len(active_orders)} aktywnych zlecen z bazy.")
        elif initial_price is not None:
            active_orders = self.place_initial_grid(initial_price)
        else:
            print("Nie udalo sie zainicjowac siatki - brak ceny startowej.")
            return

        steps = 0
        while True:
            price = self.fetch_current_price()
            if price is not None:
                if self.stop_loss_enabled and price < self.lower_price:
                    self.panic_sell(price)
                    break
                self.check_trailing(price)
                active_orders = self.monitor_grid(price)
                print(f"Bot dziala. Para: {self.symbol}, Cena: {price}")
            else:
                if self.offline and self.offline_once and self._offline_feed_exhausted:
                    print("[INFO] Offline feed consumed; exiting.")
                    break
            steps += 1
            if max_steps is not None and steps >= max_steps:
                print(f"[INFO] Reached max steps ({max_steps}); exiting.")
                break
            time.sleep(interval)

    def close(self) -> None:
        """Close SQLite connection."""
        self.storage.close()
