from dataclasses import dataclass
from typing import Any


@dataclass
class ExecutionModel:
    spread_bps: float = 0.0
    slippage_bps: float = 0.0
    apply_costs_in_price: bool = True

    def _impact_frac(self) -> float:
        half_spread = (self.spread_bps or 0.0) / 2.0
        return (half_spread + (self.slippage_bps or 0.0)) / 10000.0

    def should_fill_limit(self, side: str, level_price: float, candle_low: float, candle_high: float) -> bool:
        side_l = side.lower()
        if side_l == "buy":
            return candle_low <= level_price
        return candle_high >= level_price

    def fill_price_limit(self, side: str, level_price: float) -> float:
        impact = self._impact_frac() if self.apply_costs_in_price else 0.0
        if side.lower() == "buy":
            return level_price * (1 + impact)
        return level_price * (1 - impact)

    def cost_estimates(self, qty: float, mid_price: float):
        slip_cost = qty * mid_price * ((self.slippage_bps or 0.0) / 10000.0)
        spread_cost = qty * mid_price * (((self.spread_bps or 0.0) / 2.0) / 10000.0)
        return slip_cost, spread_cost


@dataclass
class Candle:
    open: float
    high: float
    low: float
    close: float

    @classmethod
    def from_price(cls, price: float) -> "Candle":
        return cls(open=price, high=price, low=price, close=price)
