from typing import Dict, Type

from .base import Strategy
from .classic_grid import ClassicGridStrategy


_REGISTRY: Dict[str, Type[Strategy]] = {
    "classic_grid": ClassicGridStrategy,
}


def get_strategy(strategy_id: str) -> Type[Strategy]:
    strategy = _REGISTRY.get(strategy_id)
    if not strategy:
        raise ValueError(f"Unknown strategy_id: {strategy_id}")
    return strategy

