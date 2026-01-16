import argparse
import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import yaml

from gridbot.app import main
from gridbot.core.costs import compute_grid_step_pct, recommend_grid_levels


COST_PRESETS: Dict[str, Dict[str, float]] = {
    "baseline": {"spread_bps": 20.0, "slippage_bps": 30.0, "maker_fee_bps": 2.0, "taker_fee_bps": 8.0},
    "medium": {"spread_bps": 10.0, "slippage_bps": 10.0, "maker_fee_bps": 1.0, "taker_fee_bps": 4.0},
    "ultra": {"spread_bps": 5.0, "slippage_bps": 5.0, "maker_fee_bps": 1.0, "taker_fee_bps": 2.0},
}


def parse_list(value: Optional[str], split_on_space: bool = False) -> List[str]:
    if value is None:
        return []
    if isinstance(value, Sequence) and not isinstance(value, str):
        items = []
        for v in value:
            items.extend(parse_list(v))
        return [i for i in items if i]
    sep = " " if split_on_space else ","
    parts = []
    for token in str(value).replace(",", sep).split(sep):
        token = token.strip()
        if token:
            parts.append(token)
    return parts


def ensure_report(report_path: Path, report: dict) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))


def _parse_value(raw: str):
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if "." in raw:
            val = float(raw)
            return val
        val = int(raw)
        return val
    except ValueError:
        return raw


def apply_overrides(config: dict, overrides: List[str]) -> dict:
    for item in overrides:
        if "=" not in item:
            continue
        key, raw_val = item.split("=", 1)
        val = _parse_value(raw_val.strip())
        parts = [p for p in key.split(".") if p]
        if not parts:
            continue
        cursor = config
        for idx, part in enumerate(parts):
            if idx == len(parts) - 1:
                cursor[part] = val
            else:
                if part not in cursor or not isinstance(cursor[part], dict):
                    cursor[part] = {}
                cursor = cursor[part]
    return config


def apply_cost_preset(config: dict, preset: Optional[str]) -> bool:
    """Apply named cost preset to accounting config."""
    if not preset:
        return False
    name = str(preset).lower()
    if name not in COST_PRESETS:
        raise ValueError(f"Unknown cost preset: {preset}")
    preset_vals = COST_PRESETS[name]
    acct_cfg = config.get("accounting", {})
    if not isinstance(acct_cfg, dict):
        acct_cfg = {}
    changed = False
    for key, val in preset_vals.items():
        if acct_cfg.get(key) != val:
            changed = True
        acct_cfg[key] = val
    config["accounting"] = acct_cfg
    return changed


def _coerce_float(value: Optional[object]) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _csv_low_high(path: Path) -> Tuple[float, float]:
    """Return raw low/high from OHLC CSV."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Offline CSV not found: {path}")
    low_val: Optional[float] = None
    high_val: Optional[float] = None
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("Offline CSV must include headers")
        headers = {h.lower() for h in reader.fieldnames}
        if not {"low", "high"}.issubset(headers):
            raise ValueError("Offline CSV must contain columns: low, high (plus open/close)")
        for row in reader:
            row_lower = {k.lower(): v for k, v in row.items()}
            try:
                low = float(row_lower.get("low"))
                high = float(row_lower.get("high"))
            except (TypeError, ValueError):
                continue
            low_val = low if low_val is None else min(low_val, low)
            high_val = high if high_val is None else max(high_val, high)
    if low_val is None or high_val is None:
        raise ValueError("Offline CSV low/high are empty after parsing")
    return low_val, high_val


def auto_grid_levels_from_bounds(config: dict, offline_csv: Optional[str], min_step_pct: float) -> Tuple[int, float, float, float, float, float]:
    """
    Determine grid_levels to satisfy min_step_pct.

    Returns (grid_levels, grid_step_pct, padded_lower, padded_upper, raw_low, raw_high).
    """
    lower_price = _coerce_float(config.get("lower_price"))
    upper_price = _coerce_float(config.get("upper_price"))
    raw_low = None
    raw_high = None
    padding_pct = float(config.get("csv_range_padding_pct", 0.5) or 0.0)
    if lower_price is None or upper_price is None:
        if not offline_csv:
            raise ValueError("auto-grid requires lower/upper prices or --offline-csv for CSV auto-range")
        raw_low, raw_high = _csv_low_high(Path(offline_csv))
        lower_price = raw_low * (1 - padding_pct / 100.0)
        upper_price = raw_high * (1 + padding_pct / 100.0)
    if lower_price is None or upper_price is None:
        raise ValueError("Unable to determine price bounds for auto grid search")
    if upper_price <= lower_price:
        raise ValueError(f"Invalid price bounds lower={lower_price} upper={upper_price}")
    grid_type = str(config.get("grid_type", "arithmetic"))
    min_step_pct = float(min_step_pct)
    if min_step_pct <= 0:
        raise ValueError("min_step_pct must be positive for auto grid search")
    levels = recommend_grid_levels(lower_price, upper_price, grid_type, min_step_pct, strict=True)
    step_pct = compute_grid_step_pct(lower_price, upper_price, levels, grid_type) or 0.0
    return levels, step_pct, lower_price, upper_price, raw_low, raw_high

def stub_report(run_id: str, strategy_id: str, scenario: str, seed: int, reason: str, error_type: str = "") -> dict:
    return {
        "run_id": run_id,
        "strategy_id": strategy_id,
        "scenario": scenario,
        "seed": seed,
        "status": "ERROR",
        "reason": reason,
        "error_type": error_type,
        "metrics": {},
        "risk_state": "",
        "risk_action": "",
    }


def run_once(
    out_dir: Path,
    config: Path,
    strategy_id: str,
    scenario: str,
    seed: int,
    steps: int,
    interval: float,
    base_log_level: str,
    offline_csv: Optional[str] = None,
    grid_levels: Optional[int] = None,
) -> dict:
    grid_suffix = f"_gl{grid_levels}" if grid_levels is not None else ""
    run_id = f"{strategy_id}_{scenario}_seed{seed}{grid_suffix}"
    effective_config = config
    if grid_levels is not None:
        cfg_dir = out_dir / "configs"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        cfg_path = cfg_dir / f"{config.stem}_gl{grid_levels}.yaml"
        try:
            data = yaml.safe_load(config.read_text())
            if isinstance(data, dict):
                data["grid_levels"] = grid_levels
                cfg_path.write_text(yaml.safe_dump(data))
                effective_config = cfg_path
        except Exception as exc:  # pragma: no cover
            logging.getLogger(__name__).warning(f"Could not override grid_levels in config: {exc}")
    db_path = out_dir / "db" / f"{run_id}.db"
    report_path = out_dir / "reports" / f"{run_id}.json"
    args = [
        "--config",
        str(effective_config),
        "--db-path",
        str(db_path),
        "--dry-run",
        "--offline",
        "--offline-scenario",
        scenario,
        "--offline-csv",
        offline_csv or "",
        "--seed",
        str(seed),
        "--max-steps",
        str(steps),
        "--interval",
        str(interval),
        "--reset-state",
        "--report-json",
        str(report_path),
        "--log-level",
        base_log_level,
        "--status-every-seconds",
        "0",
    ]
    report: Optional[dict] = None
    error_type = ""
    error_msg = ""
    try:
        main(args)
        if report_path.exists():
            report = json.loads(report_path.read_text())
    except SystemExit as exc:
        error_type = "SystemExit"
        error_msg = str(exc)
    except Exception as exc:  # pragma: no cover
        error_type = exc.__class__.__name__
        error_msg = str(exc)

    if report is None:
        reason = error_msg or "report_missing"
        report = stub_report(run_id, strategy_id, scenario, seed, reason=reason, error_type=error_type)
        ensure_report(report_path, report)
    else:
        report.setdefault("run_id", run_id)
        report.setdefault("strategy_id", strategy_id)
        report.setdefault("scenario", scenario)
        report.setdefault("seed", seed)
        report.setdefault("status", report.get("status") or "UNKNOWN")
        report.setdefault("reason", report.get("reason") or "")
        report.setdefault("error_type", error_type)
        report.setdefault("error_message", error_msg)
        ensure_report(report_path, report)

    metrics = report.get("metrics", {})
    return {
        "run_id": run_id,
        "strategy_id": strategy_id,
        "scenario": scenario,
        "seed": seed,
        "steps": report.get("steps"),
        "steps_completed": report.get("steps_completed", report.get("steps")),
        "status": report.get("status"),
        "reason": report.get("reason"),
        "error_type": report.get("error_type", ""),
        "error_message": report.get("error_message", ""),
        "risk_state": report.get("risk_state", ""),
        "risk_action": report.get("risk_action", ""),
        "final_equity": metrics.get("equity"),
        "pnl": metrics.get("pnl"),
        "pnl_net": metrics.get("pnl_net", metrics.get("pnl")),
        "pnl_gross": metrics.get("pnl_gross"),
        "dd_pct": metrics.get("drawdown_pct"),
        "trades": metrics.get("trades"),
        "fees": metrics.get("total_fees"),
        "total_fees_quote": metrics.get("total_fees_quote", metrics.get("total_fees")),
        "total_slippage": metrics.get("total_slippage"),
        "spread_cost_est_quote": metrics.get("spread_cost_est_quote"),
        "slippage_cost_est_quote": metrics.get("slippage_cost_est_quote"),
        "maker_fills": metrics.get("maker_fills"),
        "taker_fills": metrics.get("taker_fills"),
        "maker_ratio": metrics.get("maker_ratio"),
        "avg_fee_per_trade": metrics.get("avg_fee_per_trade"),
        "grid_step_pct": metrics.get("grid_step_pct"),
        "roundtrip_cost_pct": metrics.get("roundtrip_cost_pct"),
        "breakeven_ok": metrics.get("breakeven_ok"),
        "recommended_grid_levels": metrics.get("recommended_grid_levels"),
        "skipped_sell_no_base": report.get("accounting_skips", {}).get("skipped_sell_no_base"),
        "skipped_buy_no_quote": report.get("accounting_skips", {}).get("skipped_buy_no_quote"),
        "skipped_place_sell_no_base": metrics.get("skipped_place_sell_no_base"),
        "skipped_place_buy_no_quote": metrics.get("skipped_place_buy_no_quote"),
        "first_skip_step": metrics.get("first_skip_step"),
        "first_skip_side": metrics.get("first_skip_side"),
        "first_skip_price": metrics.get("first_skip_price"),
        "first_skip_base_free": metrics.get("first_skip_base_free"),
        "first_skip_quote_free": metrics.get("first_skip_quote_free"),
        "start_ts": report.get("start"),
        "end_ts": report.get("end"),
        "report_path": str(report_path),
        "grid_levels_used": grid_levels,
        "grid_levels_effective": metrics.get("grid_levels_effective", grid_levels),
    }


def main_cli(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Batch run offline simulations")
    parser.add_argument("--out-dir", default="out_runs/", help="Output directory for reports and DBs")
    parser.add_argument("--strategy-ids", default="classic_grid", help="Strategy ids (comma or space separated)", nargs="?")
    parser.add_argument(
        "--scenarios",
        default="range,trend_up,trend_down,flash_crash,from_csv_ohlc",
        help="Offline scenarios",
        nargs="?",
    )
    parser.add_argument("--seeds", default="1,2,3,4,5", help="Seeds", nargs="?")
    parser.add_argument("--steps", type=int, default=500, help="Max steps per run")
    parser.add_argument("--config", default="tests/fixtures/config_small.yaml", help="Path to config file")
    parser.add_argument("--offline-csv", help="Path to CSV with OHLC for from_csv_ohlc scenario")
    parser.add_argument(
        "--csv-range-padding-pct",
        type=float,
        help="Override csv_range_padding_pct when deriving bounds from CSV (from_csv_ohlc)",
    )
    parser.add_argument(
        "--auto-grid-levels",
        action="store_true",
        help="Auto-pick grid_levels so grid_step_pct >= min_step_pct using CSV bounds/padding",
    )
    parser.add_argument("--min-step-pct", type=float, help="Minimum grid step percent used by --auto-grid-levels")
    parser.add_argument(
        "--cost-preset",
        choices=sorted(COST_PRESETS.keys()),
        help="Preset for accounting costs (spread/slippage/maker/taker)",
    )
    parser.add_argument("--interval", type=float, default=0.0, help="Interval between ticks")
    parser.add_argument("--log-level", default="WARNING", help="Log level for sub-runs")
    parser.add_argument("--parallel", type=int, default=1, help="Parallel workers (>=1, currently sequential)")
    parser.add_argument("--grid-levels", help="Comma/space-separated grid_levels values to sweep", nargs="?")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on first error")
    parser.add_argument("--resume", action="store_true", help="Continue in existing out-dir instead of failing")
    parser.add_argument("--set", action="append", default=[], help="Override config values, dot notation key=value")

    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    results_file = out_dir / "results.csv"
    configs_dir = out_dir / "configs"
    reports_dir = out_dir / "reports"
    if out_dir.exists() and not args.resume:
        if results_file.exists() or configs_dir.exists() or reports_dir.exists():
            raise SystemExit("out-dir already exists with previous results; delete it or run with --resume")
    db_dir = out_dir / "db"
    for path in [db_dir, reports_dir]:
        path.mkdir(parents=True, exist_ok=True)

    if args.auto_grid_levels and args.grid_levels:
        raise SystemExit("Cannot combine --auto-grid-levels with manual --grid-levels sweep")

    # Check for conflicting csv_range_padding_pct sources
    if args.csv_range_padding_pct is not None and args.set:
        for override in args.set:
            if override.startswith("csv_range_padding_pct="):
                raise SystemExit(
                    "Cannot use both --csv-range-padding-pct flag and --set csv_range_padding_pct=... "
                    "Use one or the other to avoid ambiguity."
                )

    config_path = Path(args.config)
    try:
        cfg_data = yaml.safe_load(config_path.read_text())
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"Failed to read config: {exc}")
    if not isinstance(cfg_data, dict):
        raise SystemExit("Config file must contain a mapping at the root")

    cfg_modified = False
    try:
        preset_applied = apply_cost_preset(cfg_data, args.cost_preset)
        cfg_modified = cfg_modified or preset_applied
    except ValueError as exc:
        raise SystemExit(str(exc))
    if args.csv_range_padding_pct is not None:
        cfg_data["csv_range_padding_pct"] = float(args.csv_range_padding_pct)
        cfg_modified = True
    if args.set:
        try:
            cfg_data = apply_overrides(cfg_data, args.set)
            cfg_modified = True
        except Exception as exc:  # pragma: no cover
            raise SystemExit(f"Failed to apply overrides: {exc}")
    auto_grid = None
    auto_grid_step_pct = None
    auto_bounds: Optional[Tuple[float, float]] = None
    auto_raw_bounds: Optional[Tuple[float, float]] = None
    if args.auto_grid_levels:
        if args.min_step_pct is None:
            raise SystemExit("--min-step-pct is required with --auto-grid-levels")
        offline_csv_path = args.offline_csv or cfg_data.get("offline_csv")
        try:
            auto_grid, auto_grid_step_pct, padded_lower, padded_upper, raw_low, raw_high = auto_grid_levels_from_bounds(
                cfg_data, offline_csv_path, args.min_step_pct
            )
            auto_bounds = (padded_lower, padded_upper)
            if raw_low is not None and raw_high is not None:
                auto_raw_bounds = (raw_low, raw_high)
        except Exception as exc:
            raise SystemExit(f"Failed to auto-tune grid_levels: {exc}")
        cfg_data["grid_levels"] = auto_grid
        cfg_modified = True
        step_str = f"{auto_grid_step_pct:.4f}" if auto_grid_step_pct is not None else "unknown"
        range_str = ""
        if auto_bounds:
            range_str = f" range=[{auto_bounds[0]:.4f}, {auto_bounds[1]:.4f}]"
        if auto_raw_bounds:
            range_str += f" raw=[{auto_raw_bounds[0]:.4f}, {auto_raw_bounds[1]:.4f}]"
        print(
            f"Auto-selected grid_levels={auto_grid} (min_step_pct={args.min_step_pct}, step_pct~{step_str}{range_str})"
        )

    if cfg_modified:
        # Add batch_run metadata for audit trail
        cfg_data["_batch_run_meta"] = {
            "cost_preset_used": args.cost_preset,
            "auto_grid_levels_used": args.auto_grid_levels,
            "min_step_pct": args.min_step_pct,
            "auto_grid_step_pct": auto_grid_step_pct,
            "csv_range_padding_pct_flag": args.csv_range_padding_pct,
            "set_overrides": args.set if args.set else [],
            "config_source": str(Path(args.config).resolve()),
            "timestamp": datetime.now().isoformat(),
        }
        if auto_bounds:
            cfg_data["_batch_run_meta"]["auto_bounds"] = {
                "lower": auto_bounds[0],
                "upper": auto_bounds[1],
            }
        if auto_raw_bounds:
            cfg_data["_batch_run_meta"]["auto_raw_bounds"] = {
                "lower": auto_raw_bounds[0],
                "upper": auto_raw_bounds[1],
            }
        cfg_text = yaml.safe_dump(cfg_data, sort_keys=False)
        config_path = out_dir / "applied_config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(cfg_text)

    strategy_ids = parse_list(args.strategy_ids)
    scenarios = parse_list(args.scenarios)
    seeds = [int(s) for s in parse_list(args.seeds)]

    grid_levels_values: List[Optional[int]]
    if auto_grid is not None:
        grid_levels_values = [int(auto_grid)]
    else:
        grid_levels_list = parse_list(args.grid_levels) if args.grid_levels else []
        grid_levels_values = [int(gl) for gl in grid_levels_list] if grid_levels_list else [None]

    total_runs = len(strategy_ids) * len(scenarios) * len(seeds) * len(grid_levels_values)
    print(
        f"Preflight: strategies={strategy_ids}, scenarios={scenarios}, seeds={seeds}, "
        f"grid_levels={grid_levels_values}, total_runs={total_runs}"
    )
    if total_runs == 0:
        print("No runs scheduled. Check strategy_ids/scenarios/seeds.")
        raise SystemExit(2)

    results: List[dict] = []
    for strategy in strategy_ids:
        for scenario in scenarios:
            for grid_levels in grid_levels_values:
                for seed in seeds:
                    logging.getLogger(__name__).info(f"Running {strategy}/{scenario}/seed{seed}/gl{grid_levels}")
                    res = run_once(
                        out_dir,
                        config_path,
                        strategy,
                        scenario,
                        seed,
                        args.steps,
                        args.interval,
                        args.log_level,
                        args.offline_csv,
                        grid_levels=grid_levels,
                    )
                    # Add batch_run audit fields
                    res["cost_preset_used"] = args.cost_preset
                    res["auto_grid_levels_used"] = args.auto_grid_levels
                    res["min_step_pct_used"] = args.min_step_pct
                    results.append(res)
                    if args.fail_fast and res.get("status") == "ERROR":
                        break
                if args.fail_fast and results and results[-1].get("status") == "ERROR":
                    break
        if args.fail_fast and results and results[-1].get("status") == "ERROR":
            break

    csv_path = out_dir / "results.csv"
    fieldnames = [
        "run_id",
        "strategy_id",
        "scenario",
        "seed",
        "steps",
        "steps_completed",
        "status",
        "reason",
        "error_type",
        "error_message",
        "risk_state",
        "risk_action",
        "final_equity",
        "pnl",
        "pnl_net",
        "pnl_gross",
        "dd_pct",
        "trades",
        "fees",
        "total_fees_quote",
        "total_slippage",
        "spread_cost_est_quote",
        "slippage_cost_est_quote",
        "maker_fills",
        "taker_fills",
        "maker_ratio",
        "avg_fee_per_trade",
        "grid_step_pct",
        "roundtrip_cost_pct",
        "breakeven_ok",
        "recommended_grid_levels",
        "skipped_sell_no_base",
        "skipped_buy_no_quote",
        "skipped_place_sell_no_base",
        "skipped_place_buy_no_quote",
        "first_skip_step",
        "first_skip_side",
        "first_skip_price",
        "first_skip_base_free",
        "first_skip_quote_free",
        "start_ts",
        "end_ts",
        "report_path",
        "grid_levels_used",
        "grid_levels_effective",
        "cost_preset_used",
        "auto_grid_levels_used",
        "min_step_pct_used",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(row)

    status_counts = {}
    for r in results:
        st = (r.get("status") or "UNKNOWN").upper()
        status_counts[st] = status_counts.get(st, 0) + 1
    print("Status counts:", status_counts)

    stopped_reasons = [r.get("reason") for r in results if (r.get("status") or "").upper() == "STOPPED"]
    error_reasons = [r.get("reason") for r in results if (r.get("status") or "").upper() == "ERROR"]
    if stopped_reasons:
        print("Top STOPPED reasons:", stopped_reasons[:5])
    if error_reasons:
        print("Top ERROR reasons:", error_reasons[:5])

    ok_runs = [r for r in results if (r.get("status") or "").upper() != "ERROR"]
    if ok_runs:
        top_pnl = sorted([r for r in ok_runs if r.get("pnl") is not None], key=lambda x: x["pnl"], reverse=True)[:10]
        top_dd = sorted(
            [r for r in ok_runs if r.get("dd_pct") is not None],
            key=lambda x: x["dd_pct"],
        )[:10]

        print("TOP PnL:")
        for r in top_pnl:
            print(
                f"{r['run_id']} ({r['scenario']} seed={r['seed']} status={r.get('status')} reason={r.get('reason')}): "
                f"pnl={r.get('pnl')} dd={r.get('dd_pct')} trades={r.get('trades')} "
                f"grid_step_pct={r.get('grid_step_pct')} roundtrip_cost_pct={r.get('roundtrip_cost_pct')}"
            )

        print("TOP Low DD:")
        for r in top_dd:
            print(
                f"{r['run_id']} ({r['scenario']} seed={r['seed']} status={r.get('status')} reason={r.get('reason')}): "
                f"dd={r.get('dd_pct')} pnl={r.get('pnl')} trades={r.get('trades')} "
                f"grid_step_pct={r.get('grid_step_pct')} roundtrip_cost_pct={r.get('roundtrip_cost_pct')}"
            )
    else:
        print(f"No successful runs. Errors: {len(error_reasons)}. Top reasons: {error_reasons[:5]}")
    print(f"Results written to {csv_path}")


if __name__ == "__main__":
    main_cli()
