import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class Storage:
    """SQLite persistence layer for bot state and orders."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        """Close SQLite connection."""
        self.conn.close()

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
            try:
                self.conn.execute("ALTER TABLE bot_state ADD COLUMN status TEXT NOT NULL DEFAULT 'RUNNING'")
            except sqlite3.OperationalError:
                pass

    def load_bot_state(self) -> Optional[Tuple[float, float, str]]:
        """Load persisted price range if available."""
        cursor = self.conn.execute("SELECT lower_price, upper_price, status FROM bot_state WHERE id = 1")
        row = cursor.fetchone()
        if row:
            status = str(row["status"]) if "status" in row.keys() else "RUNNING"
            return float(row["lower_price"]), float(row["upper_price"]), status
        return None

    def save_bot_state(self, lower_price: float, upper_price: float, status: str) -> None:
        """Persist current price range so trailing survives restarts."""
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO bot_state (id, lower_price, upper_price, status) VALUES (1, ?, ?, ?)",
                (lower_price, upper_price, status),
            )

    def load_active_orders(self, order_size: float, exchange_id: str) -> List[Dict[str, Any]]:
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
                    "amount": order_size,
                    "exchange": exchange_id,
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

    def delete_active_order(self, order_id: str) -> None:
        """Remove a single active order."""
        with self.conn:
            self.conn.execute("DELETE FROM active_orders WHERE id = ?", (order_id,))

    def replace_active_order(self, old_order_id: str, new_order: Optional[Dict[str, Any]]) -> None:
        """Replace an existing active order with a new one inside a transaction."""
        with self.conn:
            self.conn.execute("DELETE FROM active_orders WHERE id = ?", (old_order_id,))
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

    def clear_active_orders(self) -> None:
        """Remove all active orders."""
        with self.conn:
            self.conn.execute("DELETE FROM active_orders")

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
