import logging
from dataclasses import dataclass
from typing import Optional, Tuple


logger = logging.getLogger(__name__)


@dataclass
class AccountingConfig:
    enabled: bool = True
    initial_usdt: float = 1000.0
    initial_base: float = 0.0
    fee_rate: float = 0.001
    slippage_bps: float = 0.0


class Accounting:
    """Simple balance tracker for dry-run/offline fills."""

    def __init__(self, config: AccountingConfig) -> None:
        self.config = config
        self.base_qty = float(config.initial_base)
        self.quote_qty = float(config.initial_usdt)
        self.peak_equity = self.equity(None)
        self.skipped_sell_no_base = 0
        self.skipped_buy_no_quote = 0
        self.trades_executed = 0

    def equity(self, price: Optional[float]) -> float:
        if price is None:
            return self.quote_qty
        return self.quote_qty + self.base_qty * price

    def apply_fee(self, value: float) -> float:
        return value * self.config.fee_rate

    def on_fill(self, side: str, price: float, qty: float) -> Tuple[bool, float, float]:
        side_l = side.lower()
        if side_l not in {"buy", "sell"}:
            return False, 0.0, self.equity(price)
        value = qty * price
        fee = self.apply_fee(value)

        if side_l == "buy":
            total_cost = value + fee
            if self.quote_qty + 1e-12 < total_cost:
                self.skipped_buy_no_quote += 1
                if self.skipped_buy_no_quote == 1:
                    logger.warning("Accounting: insufficient quote balance for BUY, skipping fill")
                else:
                    logger.debug("Accounting: insufficient quote balance for BUY, skipping fill")
                return False, 0.0, self.equity(price)
            self.quote_qty -= total_cost
            self.base_qty += qty
        else:
            if self.base_qty + 1e-12 < qty:
                self.skipped_sell_no_base += 1
                if self.skipped_sell_no_base == 1:
                    logger.warning("Accounting: insufficient base balance for SELL, skipping fill")
                else:
                    logger.debug("Accounting: insufficient base balance for SELL, skipping fill")
                return False, 0.0, self.equity(price)
            self.base_qty -= qty
            self.quote_qty += value - fee

        eq = self.equity(price)
        if eq > self.peak_equity:
            self.peak_equity = eq
        self.trades_executed += 1
        return True, fee, eq
