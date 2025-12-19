from dataclasses import dataclass


@dataclass
class ExecutionModel:
    spread_bps: float = 0.0
    slippage_bps: float = 0.0

    def _impact_frac(self) -> float:
        half_spread = (self.spread_bps or 0.0) / 2.0
        return (half_spread + (self.slippage_bps or 0.0)) / 10000.0

    def should_fill_limit(self, side: str, level_price: float, candle_low: float, candle_high: float) -> bool:
        side_l = side.lower()
        if side_l == "buy":
            return candle_low <= level_price
        return candle_high >= level_price

    def fill_price_limit(self, side: str, level_price: float) -> float:
        impact = self._impact_frac()
        if side.lower() == "buy":
            return level_price * (1 + impact)
        return level_price * (1 - impact)
