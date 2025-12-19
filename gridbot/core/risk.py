import time
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class RiskConfig:
    enabled: bool = True
    max_consecutive_errors: int = 5
    max_price_jump_pct: float = 3.0
    pause_seconds: float = 60.0
    max_drawdown_pct: float = 10.0
    panic_on_stop: bool = True
    amplitude_pct: float = 1.0
    noise_pct: float = 0.5
    period_steps: int = 24
    risk_action: str = "EXIT"


class RiskEngine:
    """Minimal risk checks for runtime safety."""

    def __init__(self, config: RiskConfig) -> None:
        self.config = config
        self.consecutive_errors = 0
        self.pause_until: Optional[float] = None
        self.peak_equity: Optional[float] = None

    def evaluate(
        self,
        price: Optional[float],
        last_price: Optional[float],
        status: str,
        error: Optional[Exception] = None,
        now: Optional[float] = None,
        equity: Optional[float] = None,
    ) -> Tuple[str, Optional[str]]:
        if not self.config.enabled:
            return status, None

        now = now or time.time()

        # If we were paused, check if we can resume
        if status == "PAUSED":
            if self.pause_until is None or now >= self.pause_until:
                self.pause_until = None
                return "RUNNING", None
            return "PAUSED", None

        if error is not None:
            self.consecutive_errors += 1
            if self.consecutive_errors >= self.config.max_consecutive_errors:
                return "STOPPED", "too_many_errors"
            return status, None

        # reset error counter on successful tick
        self.consecutive_errors = 0

        if price is None:
            return "STOPPED", "no_price"

        if last_price is not None:
            jump_pct = abs(price - last_price) / max(last_price, 1e-9) * 100
            if jump_pct > self.config.max_price_jump_pct:
                self.pause_until = now + self.config.pause_seconds
                return "PAUSED", "price_jump"

        if equity is not None and self.config.max_drawdown_pct > 0:
            if self.peak_equity is None or equity > self.peak_equity:
                self.peak_equity = equity
            dd_pct = (self.peak_equity - equity) / max(self.peak_equity, 1e-9) * 100
            if dd_pct >= self.config.max_drawdown_pct:
                return "STOPPED", "max_drawdown"

        return status, None
