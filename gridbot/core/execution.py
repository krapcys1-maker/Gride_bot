from dataclasses import dataclass
from typing import Tuple


@dataclass
class ExecutionModel:
    fee_bps: float = 0.0
    spread_bps: float = 0.0
    slippage_bps: float = 0.0
    apply_costs_in_price: bool = True

    def _impact_frac(self) -> float:
        half_spread = (self.spread_bps or 0.0) / 2.0
        return (half_spread + (self.slippage_bps or 0.0)) / 10000.0

    def execution_price(self, side: str, mid_price: float) -> float:
        impact = self._impact_frac()
        if not self.apply_costs_in_price:
            return mid_price
        if side.lower() == "buy":
            return mid_price * (1 + impact)
        return mid_price * (1 - impact)

    def fee_quote(self, notional_quote: float) -> float:
        return notional_quote * ((self.fee_bps or 0.0) / 10000.0)

    def cost_estimates(self, qty: float, mid_price: float) -> Tuple[float, float]:
        """Return (slippage_cost, spread_cost) estimated on mid price in quote."""
        slip_cost = qty * mid_price * ((self.slippage_bps or 0.0) / 10000.0)
        spread_cost = qty * mid_price * (((self.spread_bps or 0.0) / 2.0) / 10000.0)
        return slip_cost, spread_cost
