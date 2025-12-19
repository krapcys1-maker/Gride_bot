import math
from typing import Optional


def roundtrip_cost_bps(fee_bps: float, spread_bps: float, slippage_bps: float) -> float:
    """Return estimated roundtrip cost in bps."""
    return 2 * float(fee_bps) + float(spread_bps) + float(slippage_bps)


def roundtrip_cost_pct(fee_bps: float, spread_bps: float, slippage_bps: float) -> float:
    """Return estimated roundtrip cost in percent."""
    return roundtrip_cost_bps(fee_bps, spread_bps, slippage_bps) / 100.0


def grid_step_pct(lower_price: float, upper_price: float, grid_levels: int, grid_type: str) -> Optional[float]:
    """Grid step expressed as fraction (not percent)."""
    if grid_levels <= 1:
        return None
    grid_type = str(grid_type or "").lower()
    if grid_type == "geometric":
        ratio = (upper_price / lower_price) ** (1 / (grid_levels - 1))
        return ratio - 1
    mid_price = (upper_price + lower_price) / 2
    if mid_price <= 0:
        return None
    step_abs = (upper_price - lower_price) / (grid_levels - 1)
    return step_abs / mid_price


def recommend_grid_levels(lower_price: float, upper_price: float, grid_type: str, min_step_pct: float) -> int:
    """Return maximum grid_levels satisfying min_step_pct (percent)."""
    min_step_frac = min_step_pct / 100.0
    if min_step_frac <= 0:
        return 2
    grid_type = str(grid_type or "").lower()
    if grid_type == "geometric":
        levels = 1 + int(math.floor(math.log(upper_price / lower_price) / math.log(1 + min_step_frac)))
        return max(levels, 2)
    mid_price = (upper_price + lower_price) / 2
    if mid_price <= 0:
        return 2
    step_abs_needed = mid_price * min_step_frac
    if step_abs_needed <= 0:
        return 2
    levels = 1 + int(math.floor((upper_price - lower_price) / step_abs_needed))
    return max(levels, 2)


def compute_breakeven_metrics(
    lower_price: float,
    upper_price: float,
    grid_levels: int,
    grid_type: str,
    fee_bps: float,
    spread_bps: float,
    slippage_bps: float,
    safety_factor: float = 1.2,
) -> dict:
    """Pure helper returning breakeven-related metrics for a grid."""
    step_frac = grid_step_pct(lower_price, upper_price, grid_levels, grid_type)
    grid_step_pct_val = step_frac * 100 if step_frac is not None else None
    rt_bps = roundtrip_cost_bps(fee_bps, spread_bps, slippage_bps)
    rt_pct = roundtrip_cost_pct(fee_bps, spread_bps, slippage_bps)
    min_step_pct = rt_pct * safety_factor * 100
    breakeven_ok = None
    recommended_levels = None
    if grid_step_pct_val is not None:
        breakeven_ok = grid_step_pct_val >= min_step_pct
        recommended_levels = recommend_grid_levels(lower_price, upper_price, grid_type, min_step_pct)
    return {
        "grid_step_pct": grid_step_pct_val,
        "roundtrip_cost_bps": rt_bps,
        "roundtrip_cost_pct": rt_pct,
        "breakeven_ok": breakeven_ok,
        "recommended_grid_levels": recommended_levels,
        "breakeven_safety_factor": safety_factor,
    }
