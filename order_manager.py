import json
import os
from typing import List, Dict


class OrderManager:
    """Simple persistence helper for storing and retrieving order snapshots."""

    def __init__(self, filename: str = "orders.json") -> None:
        self.filename = filename

    def save_orders(self, orders: List[Dict]) -> None:
        """Persist the provided list of orders to disk as pretty JSON."""
        with open(self.filename, "w", encoding="utf-8") as handle:
            json.dump(orders, handle, indent=4)

    def load_orders(self) -> List[Dict]:
        """Reload persisted orders, returning an empty list if the file is unavailable or malformed."""
        if not os.path.exists(self.filename):
            return []

        try:
            with open(self.filename, encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):
            return []
