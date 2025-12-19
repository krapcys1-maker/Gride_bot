from typing import Any, List, Optional


class Strategy:
    """Strategy interface."""

    def __init__(self, bot: Any) -> None:
        self.bot = bot

    def on_start(self, active_orders: Optional[List[dict]] = None) -> None:
        """Called after bot initialization and active orders load."""
        return None

    def on_tick(self, price: float, active_orders: List[dict]) -> List[dict]:
        """Handle one tick and return updated active orders."""
        return active_orders

