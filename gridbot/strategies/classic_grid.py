from typing import List

from .base import Strategy


class ClassicGridStrategy(Strategy):
    """Adapter that preserves existing grid logic."""

    def on_tick(self, price: float, active_orders: List[dict]) -> List[dict]:
        bot = self.bot
        if bot.stop_loss_enabled and price < bot.lower_price:
            bot.panic_sell(price)
            return active_orders
        bot.check_trailing(price)
        return bot.monitor_grid(price)

