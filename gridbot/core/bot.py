import logging
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
from .accounting import Accounting, AccountingConfig
from .exchange import init_exchange
from gridbot.strategies import get_strategy
from .risk import RiskConfig, RiskEngine
from .storage import Storage


logger = logging.getLogger(__name__)


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
        status_every_seconds: float = 10.0,
        report_path: Optional[str] = None,
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
        self.config_path = config_path
        self.config = load_config(config_path)
        offline_requested = (
            bool(offline)
            or str(os.getenv("GRIDBOT_OFFLINE", "")).lower() in {"1", "true", "yes"}
            or bool(self.config.get("offline"))
        )
        self.offline = offline_requested
        self.offline_once = offline_once
        self.offline_scenario = offline_scenario
        self.seed = seed
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
        self.stop_reason: str = ""
        self.last_price: Optional[float] = None
        self.status_every_seconds = max(status_every_seconds, 0.0)
        self._last_status_log: float = 0.0
        self._paused_logged: bool = False
        self.report_path = report_path
        self.start_time = datetime.utcnow()
        self.end_time: Optional[datetime] = None
        self.steps_executed = 0
        self.steps_completed = 0
        self.trade_count = 0
        self.total_fees = 0.0
        self.initial_equity: Optional[float] = None
        self.strategy_id = self.config.get("strategy_id", "classic_grid")
        StrategyCls = get_strategy(self.strategy_id)
        self.strategy = StrategyCls(self)

        risk_cfg = self.config.get("risk", {})
        self.risk_engine = RiskEngine(
            RiskConfig(
                enabled=bool(risk_cfg.get("enabled", True)),
                max_consecutive_errors=int(risk_cfg.get("max_consecutive_errors", 5)),
                max_price_jump_pct=float(risk_cfg.get("max_price_jump_pct", 3.0)),
                pause_seconds=float(risk_cfg.get("pause_seconds", 60)),
                max_drawdown_pct=float(risk_cfg.get("max_drawdown_pct", 10.0)),
                panic_on_stop=bool(risk_cfg.get("panic_on_stop", True)),
            )
        )

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
        acct_cfg = self.config.get("accounting", {})
        self.accounting: Optional[Accounting] = None
        if acct_cfg.get("enabled", True) and (self.dry_run or self.offline):
            self.accounting = Accounting(
                AccountingConfig(
                    enabled=True,
                    initial_usdt=float(acct_cfg.get("initial_usdt", 1000.0)),
                    initial_base=float(acct_cfg.get("initial_base", 0.0)),
                    fee_rate=float(acct_cfg.get("fee_rate", 0.001)),
                    slippage_bps=float(acct_cfg.get("slippage_bps", 0.0)),
                )
            )
        if self.accounting:
            initial_price = self.fetch_current_price()
            self.initial_equity = self.accounting.equity(initial_price)
            if self.risk_engine.peak_equity is None and self.initial_equity is not None:
                self.risk_engine.peak_equity = self.initial_equity

    def reset_state(self) -> None:
        """Clear persisted state and revert prices to config defaults."""
        self.storage.reset_state()
        self.lower_price = float(self.config["lower_price"])
        self.upper_price = float(self.config["upper_price"])
        self.status = "RUNNING"
        self.stop_reason = ""
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
            lower_price, upper_price, status, reason = state
            self.lower_price = lower_price
            self.upper_price = upper_price
            self.status = status
            self.stop_reason = reason

    def _save_bot_state(self) -> None:
        self.storage.save_bot_state(self.lower_price, self.upper_price, self.status, self.stop_reason)

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
            amplitude_pct = float(self.config.get("risk", {}).get("amplitude_pct", 1.0))
            noise_pct = float(self.config.get("risk", {}).get("noise_pct", 0.5))
            period_steps = int(self.config.get("risk", {}).get("period_steps", 24))
            amplitude = base * (amplitude_pct / 100.0)
            noise_scale = base * (noise_pct / 100.0)
            for i in range(length):
                wave = math.sin(i / max(period_steps, 1)) * amplitude
                noise = random.uniform(-noise_scale, noise_scale)
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
                logger.warning("Offline mode: no price feed available (offline_prices or data/offline_prices.csv).")
                self._offline_feed_warned = True
            self._offline_feed_exhausted = True
            return None
        try:
            return next(self._offline_price_cycle)
        except StopIteration:
            self._offline_feed_exhausted = True
            if not getattr(self, "_offline_feed_warned", False):
                logger.warning("Offline mode: price feed exhausted.")
                self._offline_feed_warned = True
            return None

    def mark_stopped(self) -> None:
        """Persist STOPPED status."""
        self.status = "STOPPED"
        if not self.stop_reason:
            self.stop_reason = "manual_stop"
        self._save_bot_state()

    def _panic_clear_orders(self) -> None:
        """Clear active orders and cancel on exchange if live."""
        active_orders = self.load_active_orders()
        if not self.dry_run:
            for order in active_orders:
                try:
                    self.exchange.cancel_order(order["id"], self.symbol)
                except Exception as exc:  # pragma: no cover
                    logger.warning(f"Nie udalo sie anulowac zlecenia {order['id']}: {exc}")
        self.storage.clear_active_orders()

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
            logger.debug(f"[DRY RUN] plan zlecenia {side} {amount} {self.symbol} po cenie {price}")
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
                    logger.error(f"Brak ID zlecenia dla {side} {amount}@{price}")
                    return None

                raw_ts = order.get("timestamp")
                order_timestamp: str
                if isinstance(raw_ts, (int, float)):
                    order_timestamp = datetime.utcfromtimestamp(raw_ts / 1000).isoformat()
                else:
                    order_timestamp = str(order.get("datetime") or now_ts)

                status = order.get("status") or "open"
                logger.info(f"Zlozono zlecenie {order_id}: {side} {amount} {self.symbol} @ {price}")
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
                logger.critical(f"Brak srodkow dla zlecenia {side} {amount}@{price}: {exc}")
                return None
            except ccxt.NetworkError as exc:
                attempts += 1
                logger.warning(f"Problem sieci podczas skladania zlecenia {side} {amount}@{price}: {exc}")
                time.sleep(1)
                if attempts >= 2:
                    return None
            except Exception as exc:  # pragma: no cover
                logger.error(f"Nie udalo sie zlozyc zlecenia {side} {amount}@{price}: {exc}")
                return None

        return None

    def place_initial_grid(self, current_price: float) -> List[Dict[str, Any]]:
        """Simulate placing the initial grid and return the order plan."""
        orders: List[Dict[str, Any]] = []
        buys = 0
        sells = 0
        for level in self.calculator.calculate_levels():
            if level == current_price:
                continue
            side = "buy" if level < current_price else "sell"
            created = self.create_limit_order(side, level, self.order_size)
            if created:
                orders.append(created)
                if side == "buy":
                    buys += 1
                else:
                    sells += 1
        if orders:
            self.save_active_orders(orders)
            logger.info(f"Placed/Planned {buys} BUY + {sells} SELL orders")
            logger.debug(f"Szczegoly zlecen: {orders}")
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
            logger.warning(f"Problem sieci podczas pobierania statusu {order['id']}: {exc}")
            time.sleep(1)
            return "open", None, 0.0
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Nie udalo sie pobrac statusu zlecenia {order['id']}: {exc}")
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
                    logger.warning(f"Problem sieci podczas anulowania {lowest_buy['id']}: {exc}")
                    time.sleep(1)
                except Exception as exc:  # pragma: no cover
                    logger.warning(f"Nie udalo sie anulowac {lowest_buy['id']}: {exc}")
            if cancelled:
                try:
                    self.storage.delete_active_order(lowest_buy["id"])
                    orders = [o for o in orders if o["id"] != lowest_buy["id"]]
                except Exception as exc:  # pragma: no cover
                    logger.warning(f"Nie udalo sie usunac dolnego zlecenia {lowest_buy['id']}: {exc}")
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
        logger.info(f"Przesunieto siatke w gore do zakresu {new_lower}-{new_upper}")

    def panic_sell(self, current_price: float) -> None:
        """Execute stop-loss: cancel orders, liquidate base, mark bot stopped."""
        logger.warning("Cena przebila dolny zakres! Wykonano Panic Sell. Kapital zabezpieczony w USDT.")
        active_orders = self.load_active_orders()
        if not self.dry_run:
            for order in active_orders:
                try:
                    self.exchange.cancel_order(order["id"], self.symbol)
                except Exception as exc:  # pragma: no cover
                    logger.warning(f"Nie udalo sie anulowac zlecenia {order['id']}: {exc}")
        self.storage.clear_active_orders()

        base_currency = self.symbol.split("/")[0]
        if not self.dry_run:
            try:
                balance = self.exchange.fetch_balance()
                base_free = float(balance.get(base_currency, {}).get("free", 0) or 0)
            except Exception as exc:  # pragma: no cover
                base_free = 0.0
                logger.warning(f"Nie udalo sie pobrac balansu do panic sell: {exc}")
            if base_free > 0:
                try:
                    self.exchange.create_order(self.symbol, "market", "sell", base_free)
                    logger.info(f"Sprzedano {base_free} {base_currency} po cenie rynkowej")
                except Exception as exc:  # pragma: no cover
                    logger.warning(f"Nie udalo sie zrealizowac panic sell: {exc}")

        self.status = "STOPPED"
        self.stop_reason = "panic_sell"
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
                    logger.warning(f"Nie udalo sie usunac anulowanego zlecenia {order['id']}: {exc}")
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
            equity_after = None
            fee_used = None
            if self.accounting:
                ok, fee, equity_after = self.accounting.on_fill(order["side"], execution_price, filled_amount)
                if not ok:
                    try:
                        self.storage.delete_active_order(order["id"])
                        updated_orders.remove(order)
                    except Exception as exc:  # pragma: no cover
                        logger.warning(f"Nie udalo sie usunac zlecenia po odrzuceniu fillu {order['id']}: {exc}")
                    modified = True
                    continue
                fee_used = fee
            if fee_used is None:
                fee_used = trade_data["fee_estimated"]
            trade_data["fee"] = fee_used
            trade_data["equity_after"] = equity_after
            self.log_trade(trade_data)
            self.trade_count += 1
            try:
                self.total_fees += float(trade_data.get("fee") or 0.0)
            except Exception:
                pass

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
                logger.warning(f"Blad podczas aktualizacji bazy dla zlecenia {order['id']}: {exc}")

        if modified:
            self.save_active_orders(updated_orders)

        return updated_orders

    def fetch_current_price(self) -> Optional[float]:
        """Fetch latest price for configured symbol."""
        if self.offline:
            price = self._next_offline_price()
            if price is None and self.offline_once:
                logger.info("Offline feed finished; stopping bot.")
            return price
        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            return ticker.get("last") or ticker.get("close")
        except Exception as exc:  # pragma: no cover
            logger.error(f"Blad podczas pobierania tickera: {exc}")
            return None

    def risk_check(self, current_price: Optional[float]) -> None:
        """Warn the operator when potential profit per grid is below exchange fees."""
        if current_price is None:
            return

        if self.grid_ratio:
            profit_percent = (self.grid_ratio - 1)
            logger.info(f"Siatka (geometric): krok ~{profit_percent*100:.4f}%")
        else:
            grid_range = float(self.upper_price) - float(self.lower_price)
            profit_percent = (grid_range / self.grid_levels) / current_price
            logger.info(f"Siatka: skok co {grid_range / self.grid_levels:.2f} (~{profit_percent*100:.4f}%)")
        if profit_percent < 0.002:
            logger.warning("!" * 50)
            logger.warning(f"CRITICAL WARNING: zysk na kratce to tylko {profit_percent*100:.4f}%!")
            logger.warning("Gielda pobiera ok. 0.1% - 0.2% prowizji (entry + exit).")
            logger.warning("Sugerowane: zmniejsz liczbe grid_levels lub zwieksz zakres.")
            logger.warning("!" * 50)
            time.sleep(5)

    def run(self, interval: float = 10.0, max_steps: Optional[int] = None) -> None:
        """Start the bot loop: load state, fetch price, and monitor the grid."""
        if self.dry_run:
            logger.info("Dry-run mode: skipping balance check.")
        else:
            try:
                balance = self.exchange.fetch_balance()
                logger.info("Balance fetched, exchange keys look valid.")
            except Exception as exc:  # pragma: no cover
                logger.error(f"Unable to fetch balance: {exc}")

        initial_price = self.fetch_current_price()
        self.risk_check(initial_price)

        active_orders = self.load_active_orders()
        if active_orders:
            logger.info(f"Zaladowano {len(active_orders)} aktywnych zlecen z bazy.")
        elif initial_price is not None:
            active_orders = self.place_initial_grid(initial_price)
        else:
            logger.error("Nie udalo sie zainicjowac siatki - brak ceny startowej.")
            return

        self._save_bot_state()
        self.strategy.on_start(active_orders)
        self.last_price = initial_price
        steps = 0
        while True:
            try:
                price = self.fetch_current_price()
                equity = self.accounting.equity(price) if self.accounting else None
                new_status, risk_reason = self.risk_engine.evaluate(
                    price, self.last_price, self.status, now=time.time(), equity=equity
                )
            except Exception as exc:
                logger.error(f"Unexpected error in price fetch: {exc}")
                new_status, risk_reason = self.risk_engine.evaluate(
                    None, self.last_price, self.status, error=exc, now=time.time(), equity=None
                )
                if new_status != self.status or (risk_reason and risk_reason != self.stop_reason):
                    self.status = new_status
                    if risk_reason:
                        self.stop_reason = risk_reason
                    self._save_bot_state()
                if self.status == "STOPPED":
                    if self.risk_engine.config.panic_on_stop:
                        self._panic_clear_orders()
                    break
                time.sleep(interval)
                continue

            if new_status != self.status or (risk_reason and risk_reason != self.stop_reason):
                previous_status = self.status
                self.status = new_status
                self.stop_reason = risk_reason or ""
                self._save_bot_state()
                if previous_status == "PAUSED" and self.status == "RUNNING":
                    logger.info("Bot resumed")
                    self._paused_logged = False

            if self.status == "STOPPED":
                if self.risk_engine.config.panic_on_stop:
                    self._panic_clear_orders()
                break

            if self.status == "PAUSED":
                if not self.stop_reason and risk_reason:
                    self.stop_reason = risk_reason
                if not getattr(self, "_paused_logged", False):
                    logger.info(
                        f"Bot paused (reason={self.stop_reason or risk_reason or 'pause'}, for={self.risk_engine.config.pause_seconds}s)"
                    )
                    self._paused_logged = True
                else:
                    logger.debug("Bot paused; waiting to resume")
                steps += 1
                if max_steps is not None and steps >= max_steps:
                    logger.info(f"Reached max steps ({max_steps}); exiting.")
                    break
                sleep_time = interval if interval > 0 else min(self.risk_engine.config.pause_seconds, 1.0)
                time.sleep(sleep_time)
                continue

            if price is not None:
                try:
                    active_orders = self.strategy.on_tick(price, active_orders)
                    now_ts = time.time()
                    if self.status_every_seconds <= 0:
                        logger.debug(f"Bot dziala. Para: {self.symbol}, Cena: {price}")
                    elif now_ts - self._last_status_log >= self.status_every_seconds:
                        hb_equity = None
                        dd_pct = 0.0
                        if self.accounting:
                            hb_equity = self.accounting.equity(price)
                            peak = self.risk_engine.peak_equity or hb_equity or 1e-9
                            dd_pct = ((peak - (hb_equity or 0)) / peak) * 100 if peak else 0.0
                        pnl = (
                            (hb_equity - self.initial_equity)
                            if self.accounting and self.initial_equity is not None and hb_equity is not None
                            else None
                        )
                        base_qty = self.accounting.base_qty if self.accounting else 0.0
                        quote_qty = self.accounting.quote_qty if self.accounting else 0.0
                        eq_str = f"{hb_equity:.2f}" if hb_equity is not None else "n/a"
                        pnl_str = f"{pnl:.2f}" if pnl is not None else "n/a"
                        logger.info(
                            f"Bot dziala. Para: {self.symbol}, Cena: {price}, base={base_qty:.6f}, quote={quote_qty:.2f}, equity={eq_str}, pnl={pnl_str}, dd={dd_pct:.2f}%"
                        )
                        self._last_status_log = now_ts
                    else:
                        logger.debug(f"Cena: {price}")
                    if self.accounting:
                        equity = self.accounting.equity(price)
                        self.storage.save_equity_snapshot(datetime.utcnow().isoformat(), price, self.accounting.base_qty, self.accounting.quote_qty, equity)
                except Exception as exc:
                    logger.error(f"Error in monitor loop: {exc}")
                    new_status, risk_reason = self.risk_engine.evaluate(
                        None, self.last_price, self.status, error=exc, now=time.time(), equity=None
                    )
                    if new_status != self.status or (risk_reason and risk_reason != self.stop_reason):
                        self.status = new_status
                        if risk_reason:
                            self.stop_reason = risk_reason
                        self._save_bot_state()
                    if self.status == "STOPPED":
                        if self.risk_engine.config.panic_on_stop:
                            self._panic_clear_orders()
                        break
                    time.sleep(interval)
                    continue
                self.last_price = price
            else:
                if self.offline and self.offline_once and self._offline_feed_exhausted:
                    logger.info("Offline feed consumed; exiting.")
                    break
            steps += 1
            self.steps_executed = steps
            if max_steps is not None and steps >= max_steps:
                logger.info(f"Reached max steps ({max_steps}); exiting.")
                if self.status == "RUNNING":
                    self.status = "COMPLETED"
                    if not self.stop_reason:
                        self.stop_reason = "max_steps"
                break
            time.sleep(interval)
        self.end_time = datetime.utcnow()
        return self._final_report()

    def close(self) -> None:
        """Close SQLite connection."""
        self.storage.close()

    def _config_hash(self) -> Optional[str]:
        try:
            import hashlib

            data = self.config_path.read_bytes()
            return hashlib.sha1(data).hexdigest()
        except Exception:
            return None

    def _final_report(self) -> Dict[str, Any]:
        price = self.last_price
        equity = self.accounting.equity(price) if self.accounting else None
        peak = self.risk_engine.peak_equity if self.risk_engine else None
        dd_pct = None
        if equity is not None and peak:
            dd_pct = (peak - equity) / max(peak, 1e-9) * 100
        pnl = None
        if self.accounting and self.initial_equity is not None and equity is not None:
            pnl = equity - self.initial_equity
        accounting_skips = {}
        if self.accounting:
            accounting_skips = {
                "skipped_sell_no_base": self.accounting.skipped_sell_no_base,
                "skipped_buy_no_quote": self.accounting.skipped_buy_no_quote,
            }
        report = {
            "config_path": str(self.config_path),
            "config_hash": self._config_hash(),
            "offline": self.offline,
            "scenario": self.offline_scenario,
            "seed": self.seed,
            "status": self.status,
            "reason": self.stop_reason,
            "steps": self.steps_executed,
            "steps_completed": self.steps_executed,
            "start": self.start_time.isoformat() if self.start_time else None,
            "end": self.end_time.isoformat() if self.end_time else None,
            "metrics": {
                "price": price,
                "equity": equity,
                "pnl": pnl,
                "peak_equity": peak,
                "drawdown_pct": dd_pct,
                "trades": self.trade_count,
                "total_fees": self.total_fees,
            },
            "accounting_skips": accounting_skips,
        }
        logger.info(
            f"Raport koncowy: equity={equity}, pnl={pnl}, trades={self.trade_count}, fees={self.total_fees}, dd%={dd_pct}"
        )
        return report
