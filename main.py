import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import ccxt
from dotenv import load_dotenv
import yaml

from grid_logic import GridCalculator


DRY_RUN = True
CONFIG_FILE = Path("config.yaml")
DB_FILE = Path("grid_bot.db")


class GridBot:
    """Grid trading bot with SQLite persistence for orders and trade history."""

    def __init__(
        self,
        config_path: Path = CONFIG_FILE,
        db_path: Path = DB_FILE,
        dry_run: bool = DRY_RUN,
    ) -> None:
        self.dry_run = dry_run
        self.config = self.load_config(config_path)
        self.symbol = str(self.config["symbol"])
        self.order_size = float(self.config["order_size"])
        self.grid_levels = int(self.config["grid_levels"])
        self.lower_price = float(self.config["lower_price"])
        self.upper_price = float(self.config["upper_price"])
        self.grid_type = str(self.config.get("grid_type", "arithmetic"))
        self.trailing_up = bool(self.config["trailing_up"])
        self.stop_loss_enabled = bool(self.config["stop_loss_enabled"])
        self.status = "RUNNING"

        self.exchange = self.init_exchange()

        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
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

    @staticmethod
    def load_config(path: Path = CONFIG_FILE) -> Dict[str, Any]:
        """Load strategy settings required for the grid calculator."""
        if not path.exists():
            raise FileNotFoundError(f"{path} is missing")

        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)

        if not isinstance(data, dict):
            raise ValueError("config.yaml must contain a mapping at the root level")

        required = {"symbol", "lower_price", "upper_price", "grid_levels", "order_size"}
        missing = required.difference(data)
        if missing:
            raise ValueError(f"config.yaml missing required keys: {', '.join(sorted(missing))}")

        data["lower_price"] = float(data["lower_price"])
        data["upper_price"] = float(data["upper_price"])
        data["grid_levels"] = int(data["grid_levels"])
        data["order_size"] = float(data["order_size"])
        data["trailing_up"] = bool(data.get("trailing_up", False))
        data["stop_loss_enabled"] = bool(data.get("stop_loss_enabled", True))
        data["grid_type"] = str(data.get("grid_type", "arithmetic")).lower()
        return data

    @staticmethod
    def init_exchange() -> ccxt.Exchange:
        """Configure the ccxt KuCoin client using environment credentials."""
        load_dotenv()
        api_key = os.getenv("KUCOIN_API_KEY")
        api_secret = os.getenv("KUCOIN_API_SECRET")
        passphrase = os.getenv("KUCOIN_PASSPHRASE")
        if not api_key or not api_secret or not passphrase:
            raise EnvironmentError(
                "KUCOIN_API_KEY, KUCOIN_API_SECRET and KUCOIN_PASSPHRASE must be set in the environment"
            )

        return ccxt.kucoin(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "password": passphrase,
                "enableRateLimit": True,
            }
        )

    def _init_db(self) -> None:
        """Create tables for active orders and trade history if needed."""
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS active_orders (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    price REAL NOT NULL,
                    side TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trades_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    amount REAL NOT NULL,
                    value REAL NOT NULL,
                    fee_estimated REAL NOT NULL
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    lower_price REAL NOT NULL,
                    upper_price REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'RUNNING'
                )
                """
            )
            # Attempt to backfill status column if upgrading
            try:
                self.conn.execute("ALTER TABLE bot_state ADD COLUMN status TEXT NOT NULL DEFAULT 'RUNNING'")
            except sqlite3.OperationalError:
                pass

    def _load_bot_state(self) -> None:
        """Load persisted price range if available."""
        cursor = self.conn.execute("SELECT lower_price, upper_price, status FROM bot_state WHERE id = 1")
        row = cursor.fetchone()
        if row:
            self.lower_price = float(row["lower_price"])
            self.upper_price = float(row["upper_price"])
            self.status = str(row["status"]) if "status" in row.keys() else "RUNNING"

    def _save_bot_state(self) -> None:
        """Persist current price range so trailing survives restarts."""
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO bot_state (id, lower_price, upper_price, status) VALUES (1, ?, ?, ?)",
                (self.lower_price, self.upper_price, self.status),
            )

    def load_active_orders(self) -> List[Dict[str, Any]]:
        """Load currently active grid orders from SQLite."""
        cursor = self.conn.execute(
            "SELECT id, symbol, price, side, status, timestamp FROM active_orders WHERE status = 'open'"
        )
        orders: List[Dict[str, Any]] = []
        for row in cursor.fetchall():
            orders.append(
                {
                    "id": row["id"],
                    "symbol": row["symbol"],
                    "price": float(row["price"]),
                    "side": row["side"],
                    "amount": self.order_size,
                    "exchange": getattr(self.exchange, "id", "exchange"),
                    "status": row["status"],
                    "timestamp": row["timestamp"],
                }
            )
        return orders

    def save_active_orders(self, orders: List[Dict[str, Any]]) -> None:
        """Persist the snapshot of active orders to SQLite."""
        with self.conn:
            self.conn.execute("DELETE FROM active_orders")
            for order in orders:
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO active_orders (id, symbol, price, side, status, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order["id"],
                        order["symbol"],
                        float(order["price"]),
                        order["side"],
                        order.get("status", "open"),
                        order.get("timestamp", datetime.utcnow().isoformat()),
                    ),
                )

    def log_trade(self, trade_data: Dict[str, Any]) -> None:
        """Insert executed trade data into trade history."""
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO trades_history (timestamp, symbol, side, price, amount, value, fee_estimated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_data["timestamp"],
                    trade_data["symbol"],
                    trade_data["side"],
                    float(trade_data["price"]),
                    float(trade_data["amount"]),
                    float(trade_data["value"]),
                    float(trade_data["fee_estimated"]),
                ),
            )
        print(
            f"[ACCOUNTING] zapisano transakcje: {trade_data['side']} {trade_data['amount']} "
            f"{trade_data['symbol']} po {trade_data['price']}"
        )

    def create_limit_order(self, side: str, price: float, amount: float) -> Optional[Dict[str, Any]]:
        """Place a limit order (real or simulated) and return stored representation."""
        now_ts = datetime.utcnow().isoformat()
        exchange_id = getattr(self.exchange, "id", "exchange")

        if self.dry_run:
            order_id = f"sim_{self.symbol}_{price}"
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
                    with self.conn:
                        self.conn.execute("DELETE FROM active_orders WHERE id = ?", (lowest_buy["id"],))
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
        print("[ALARM] Cena przebiła dolny zakres! Wykonano Panic Sell. Kapitał zabezpieczony w USDT.")
        active_orders = self.load_active_orders()
        if not self.dry_run:
            for order in active_orders:
                try:
                    self.exchange.cancel_order(order["id"], self.symbol)
                except Exception as exc:  # pragma: no cover
                    print(f"[WARN] Nie udalo sie anulowac zlecenia {order['id']}: {exc}")
        with self.conn:
            self.conn.execute("DELETE FROM active_orders")

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
                    with self.conn:
                        self.conn.execute("DELETE FROM active_orders WHERE id = ?", (order["id"],))
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
                with self.conn:
                    self.conn.execute("DELETE FROM active_orders WHERE id = ?", (order["id"],))
                    if new_order:
                        self.conn.execute(
                            """
                            INSERT OR REPLACE INTO active_orders (id, symbol, price, side, status, timestamp)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                new_order["id"],
                                new_order["symbol"],
                                float(new_order["price"]),
                                new_order["side"],
                                new_order.get("status", "open"),
                                new_order.get("timestamp", datetime.utcnow().isoformat()),
                            ),
                        )
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

    def run(self) -> None:
        """Start the bot loop: load state, fetch price, and monitor the grid."""
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

        while True:
            price = self.fetch_current_price()
            if price is not None:
                if self.stop_loss_enabled and price < self.lower_price:
                    self.panic_sell(price)
                    break
                self.check_trailing(price)
                active_orders = self.monitor_grid(price)
                print(f"Bot dziala. Para: {self.symbol}, Cena: {price}")
            time.sleep(10)

    def close(self) -> None:
        """Close SQLite connection."""
        self.conn.close()


def main() -> None:
    bot = GridBot()
    try:
        bot.run()
    finally:
        bot.close()


if __name__ == "__main__":
    main()
