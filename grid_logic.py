from dataclasses import dataclass
from typing import List


@dataclass
class GridCalculator:
    """Calculate evenly spaced price levels for a grid strategy."""

    lower_price: float
    upper_price: float
    grid_levels: int

    def __post_init__(self) -> None:
        if self.lower_price <= 0:
            raise ValueError("lower_price must be greater than 0")
        if self.upper_price <= 0:
            raise ValueError("upper_price must be greater than 0")
        if self.grid_levels <= 0:
            raise ValueError("grid_levels must be greater than 0")
        if self.upper_price <= self.lower_price:
            raise ValueError("upper_price must be greater than lower_price")

    def calculate_levels(self) -> List[float]:
        """Return arithmetic grid prices from lower_price to upper_price inclusive."""
        step = (self.upper_price - self.lower_price) / self.grid_levels
        return [round(self.lower_price + step * i, 10) for i in range(self.grid_levels + 1)]
