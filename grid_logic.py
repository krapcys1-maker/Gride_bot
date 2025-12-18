from dataclasses import dataclass
from typing import List, Literal, Optional


GridType = Literal["arithmetic", "geometric"]


@dataclass
class GridCalculator:
    """Calculate price levels for a grid strategy."""

    lower_price: float
    upper_price: float
    grid_levels: int
    grid_type: GridType = "arithmetic"

    def __post_init__(self) -> None:
        if self.lower_price <= 0:
            raise ValueError("lower_price must be greater than 0")
        if self.upper_price <= 0:
            raise ValueError("upper_price must be greater than 0")
        if self.grid_levels <= 0:
            raise ValueError("grid_levels must be greater than 0")
        if self.upper_price <= self.lower_price:
            raise ValueError("upper_price must be greater than lower_price")
        if self.grid_type not in ("arithmetic", "geometric"):
            raise ValueError("grid_type must be 'arithmetic' or 'geometric'")

    @property
    def step(self) -> Optional[float]:
        if self.grid_type == "arithmetic":
            return (self.upper_price - self.lower_price) / self.grid_levels
        return None

    @property
    def ratio(self) -> Optional[float]:
        if self.grid_type == "geometric":
            return (self.upper_price / self.lower_price) ** (1 / self.grid_levels)
        return None

    def calculate_levels(self) -> List[float]:
        """Return grid prices from lower_price to upper_price inclusive."""
        if self.grid_type == "geometric":
            ratio = self.ratio or 1
            return [round(self.lower_price * (ratio**i), 10) for i in range(self.grid_levels + 1)]

        step = self.step or 0
        return [round(self.lower_price + step * i, 10) for i in range(self.grid_levels + 1)]
