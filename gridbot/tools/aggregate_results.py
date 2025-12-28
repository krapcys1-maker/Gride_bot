import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Tuple


def parse_weights(raw: str) -> Dict[str, float]:
    weights: Dict[str, float] = {}
    if not raw:
        return weights
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for part in parts:
        if "=" not in part:
            raise SystemExit(f"Invalid weight fragment (expected scenario=weight): {part}")
        scenario, val = part.split("=", 1)
        try:
            weights[scenario.strip()] = float(val)
        except ValueError:
            raise SystemExit(f"Invalid weight for scenario {scenario}: {val}")
    return weights


def _ensure_columns(fieldnames: List[str], dir_name: str) -> Tuple[str, str]:
    required = ["scenario", "status", "reason", "pnl", "trades"]
    missing = [c for c in required if c not in fieldnames]
    if missing:
        raise SystemExit(f"{dir_name}: results.csv missing required columns: {', '.join(missing)}")

    if "grid_levels" in fieldnames:
        grid_col = "grid_levels"
    elif "grid_levels_used" in fieldnames:
        grid_col = "grid_levels_used"
    else:
        raise SystemExit(f"{dir_name}: results.csv missing grid_levels/grid_levels_used column")

    if "dd" in fieldnames:
        dd_col = "dd"
    elif "dd_pct" in fieldnames:
        dd_col = "dd_pct"
    else:
        raise SystemExit(f"{dir_name}: results.csv missing dd/dd_pct column")
    return grid_col, dd_col


def load_results(in_dir: Path) -> List[Dict[str, str]]:
    results_path = in_dir / "results.csv"
    if not results_path.exists():
        raise SystemExit(f"Missing results.csv in {in_dir}")
    with results_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        grid_col, dd_col = _ensure_columns(reader.fieldnames or [], in_dir.name)
        rows: List[Dict[str, str]] = []
        for row in reader:
            normalized = {
                "config": in_dir.name,
                "scenario": row.get("scenario", "").strip(),
                "grid_levels": row.get(grid_col, "").strip(),
                "status": (row.get("status") or "").strip().upper(),
                "reason": (row.get("reason") or "").strip(),
                "pnl": row.get("pnl", "").strip(),
                "dd": row.get(dd_col, "").strip(),
                "trades": row.get("trades", "").strip(),
            }
            rows.append(normalized)
    return rows


def _safe_float(val: str) -> float:
    try:
        return float(val)
    except Exception:
        return 0.0


def _safe_int(val: str) -> int:
    try:
        return int(val)
    except Exception:
        return 0


def aggregate_avg(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    agg: Dict[Tuple[str, str, str], Dict[str, float]] = {}
    for row in rows:
        key = (row["config"], row["scenario"], row["grid_levels"])
        bucket = agg.setdefault(
            key,
            {"runs": 0, "pnl_sum": 0.0, "dd_sum": 0.0, "trades_sum": 0.0, "stopped": 0, "completed": 0},
        )
        bucket["runs"] += 1
        bucket["pnl_sum"] += _safe_float(row["pnl"])
        bucket["dd_sum"] += _safe_float(row["dd"])
        bucket["trades_sum"] += _safe_float(row["trades"])
        status = row["status"]
        if status == "STOPPED":
            bucket["stopped"] += 1
        if status == "COMPLETED":
            bucket["completed"] += 1
    out: List[Dict[str, str]] = []
    for (config, scenario, grid_levels), vals in agg.items():
        runs = max(vals["runs"], 1)
        out.append(
            {
                "config": config,
                "scenario": scenario,
                "grid_levels": grid_levels,
                "runs": str(int(vals["runs"])),
                "avg_pnl": f"{vals['pnl_sum'] / runs:.10g}",
                "avg_dd": f"{vals['dd_sum'] / runs:.10g}",
                "avg_trades": f"{vals['trades_sum'] / runs:.10g}",
                "stopped": str(int(vals["stopped"])),
                "completed": str(int(vals["completed"])),
            }
        )
    return out


def aggregate_status_counts(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    agg: Dict[Tuple[str, str, str, str], int] = {}
    for row in rows:
        key = (row["config"], row["scenario"], row["grid_levels"], row["status"])
        agg[key] = agg.get(key, 0) + 1
    out: List[Dict[str, str]] = []
    for (config, scenario, grid_levels, status), count in agg.items():
        out.append(
            {
                "config": config,
                "scenario": scenario,
                "grid_levels": grid_levels,
                "status": status,
                "count": str(count),
            }
        )
    return out


def aggregate_stopped_reasons(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    agg: Dict[Tuple[str, str, str, str], int] = {}
    for row in rows:
        if row["status"] != "STOPPED":
            continue
        key = (row["config"], row["scenario"], row["grid_levels"], row["reason"])
        agg[key] = agg.get(key, 0) + 1
    out = [
        {
            "config": config,
            "scenario": scenario,
            "grid_levels": grid_levels,
            "reason": reason,
            "count": str(count),
        }
        for (config, scenario, grid_levels, reason), count in sorted(agg.items(), key=lambda x: x[1], reverse=True)
    ]
    return out


def weighted_rank(
    avg_rows: List[Dict[str, str]], weights: Dict[str, float], strict: bool, profit_scenarios: List[str]
) -> List[Dict[str, str]]:
    if not profit_scenarios:
        return []
    profit_set = set(profit_scenarios)
    profit_scenarios_present = {row["scenario"] for row in avg_rows if row["scenario"] in profit_set}
    missing_weights = profit_scenarios_present.difference(weights.keys())
    if missing_weights:
        msg = f"Missing weights for scenarios: {', '.join(sorted(missing_weights))}"
        if strict:
            raise SystemExit(msg)
        else:
            print(f"Warning: {msg}. Using weight=0 for them.", file=sys.stderr)
            for scen in missing_weights:
                weights.setdefault(scen, 0.0)

    agg: Dict[Tuple[str, str], Dict[str, float]] = {}
    for row in avg_rows:
        if row["scenario"] not in profit_set:
            continue
        key = (row["config"], row["grid_levels"])
        bucket = agg.setdefault(key, {})
        bucket[row["scenario"]] = _safe_float(row["avg_pnl"])

    scenarios = ["range", "trend_up", "trend_down", "flash_crash"]
    ranked: List[Dict[str, str]] = []
    for (config, grid_levels), scenario_map in agg.items():
        weighted_score = 0.0
        for scen, weight in weights.items():
            weighted_score += weight * scenario_map.get(scen, 0.0)
        row_out = {
            "config": config,
            "grid_levels": grid_levels,
            "weighted_score": f"{weighted_score:.10g}",
        }
        for scen in scenarios:
            row_out[f"avg_pnl_{scen}"] = f"{scenario_map.get(scen, 0.0):.10g}"
        ranked.append(row_out)

    ranked.sort(key=lambda r: float(r["weighted_score"]), reverse=True)
    for idx, row in enumerate(ranked, start=1):
        row["rank"] = str(idx)
    return ranked


def compute_gates(
    rows: List[Dict[str, str]],
    gate_scenarios: List[str],
    gate_max_loss_quote: float,
    gate_max_dd_pct: float,
    avg_lookup: Dict[Tuple[str, str, str], Dict[str, float]],
) -> List[Dict[str, str]]:
    gate_set = set(gate_scenarios)
    agg: Dict[Tuple[str, str, str], Dict[str, int]] = {}
    for row in rows:
        scenario = row["scenario"]
        if scenario not in gate_set:
            continue
        key = (row["config"], row["grid_levels"], scenario)
        bucket = agg.setdefault(key, {"runs": 0, "stopped": 0, "inventory_drawdown_runs": 0, "trade_runs": 0})
        bucket["runs"] += 1
        if row["status"] == "STOPPED":
            bucket["stopped"] += 1
        if (row.get("reason") or "") == "inventory_drawdown":
            bucket["inventory_drawdown_runs"] += 1
        if _safe_float(row.get("trades", "0")) > 0:
            bucket["trade_runs"] += 1
    # precompute stopped reason counts
    reason_counts: Dict[Tuple[str, str, str], Dict[str, int]] = {}
    for row in rows:
        if row["scenario"] not in gate_set or row["status"] != "STOPPED":
            continue
        key = (row["config"], row["grid_levels"], row["scenario"])
        bucket = reason_counts.setdefault(key, {})
        reason = row.get("reason") or ""
        bucket[reason] = bucket.get(reason, 0) + 1
    out: List[Dict[str, str]] = []
    for (config, grid_levels, scenario), vals in agg.items():
        avg_key = (config, scenario, grid_levels)
        avg_vals = avg_lookup.get(avg_key, {})
        avg_pnl = avg_vals.get("avg_pnl", 0.0)
        avg_dd = avg_vals.get("avg_dd", 0.0)
        avg_trades = avg_vals.get("avg_trades", 0.0)
        gate_pass = (avg_pnl >= -gate_max_loss_quote) and (avg_dd <= gate_max_dd_pct)
        reasons = reason_counts.get((config, grid_levels, scenario), {})
        if reasons:
            top_reason, top_count = sorted(reasons.items(), key=lambda x: x[1], reverse=True)[0]
            stopped_top = f"{top_reason}:{top_count}"
        else:
            stopped_top = ""
        out.append(
            {
                "config": config,
                "grid_levels": grid_levels,
                "scenario": scenario,
                "runs": str(vals["runs"]),
                "stopped": str(vals["stopped"]),
                "inventory_drawdown_runs": str(vals["inventory_drawdown_runs"]),
                "trade_runs": str(vals["trade_runs"]),
                "avg_pnl": f"{avg_pnl:.10g}",
                "avg_dd_pct": f"{avg_dd:.10g}",
                "avg_trades": f"{avg_trades:.10g}",
                "stopped_reasons_top": stopped_top,
                "gate_pass": "true" if gate_pass else "false",
            }
        )
    return out


def write_csv(path: Path, rows: List[Dict[str, str]], headers: List[str] = None) -> None:
    if not rows and not headers:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if headers is None:
        headers = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def print_top_weighted(path: Path, rows: List[Dict[str, str]], limit: int = 10) -> None:
    if not rows:
        print("No profitability ranking computed (no profit scenarios).")
        return
    print(f"Weighted rank written to {path}")
    print("Top profitability results:")
    for row in rows[:limit]:
        print(
            f"{row.get('rank')} {row.get('config')} gl={row.get('grid_levels')} score={row.get('weighted_score')} "
            f"range={row.get('avg_pnl_range')} trend_up={row.get('avg_pnl_trend_up')} "
            f"trend_down={row.get('avg_pnl_trend_down')} flash_crash={row.get('avg_pnl_flash_crash')}"
        )


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Aggregate results.csv across multiple runs")
    parser.add_argument("--in-dirs", required=True, help="Comma-separated list of input directories")
    parser.add_argument("--out-dir", required=True, help="Output directory for aggregated CSVs")
    parser.add_argument("--weights", default="", help="Scenario weights, e.g. range=0.5,trend_up=0.2")
    parser.add_argument("--strict", action="store_true", help="Fail if weights missing for any scenario in data")
    parser.add_argument(
        "--profit-scenarios",
        default="range,trend_up,trend_down",
        help="Comma-separated scenarios used for profitability ranking",
    )
    parser.add_argument(
        "--gate-scenarios",
        default="flash_crash",
        help="Comma-separated scenarios used for gate checks (risk)",
    )
    parser.add_argument(
        "--gate-max-loss-quote",
        type=float,
        default=0.0,
        help="Max allowed average pnl loss (quote) to pass gate (default: 0.0)",
    )
    parser.add_argument(
        "--gate-max-dd-pct",
        type=float,
        default=2.0,
        help="Max allowed average drawdown pct to pass gate (default: 2.0)",
    )
    args = parser.parse_args(argv)

    in_dirs = [Path(p.strip()) for p in args.in_dirs.split(",") if p.strip()]
    if not in_dirs:
        raise SystemExit("No input directories provided")

    weights = parse_weights(args.weights)
    profit_raw = (args.profit_scenarios or "").strip()
    if profit_raw.lower() in {"", "none", "-"}:
        profit_scenarios = []
    else:
        profit_scenarios = [s.strip() for s in profit_raw.split(",") if s.strip()]
    gate_scenarios = [s.strip() for s in args.gate_scenarios.split(",") if s.strip()]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_rows: List[Dict[str, str]] = []
    for d in in_dirs:
        all_rows.extend(load_results(d))

    avg_rows = aggregate_avg(all_rows)
    status_rows = aggregate_status_counts(all_rows)
    stopped_rows = aggregate_stopped_reasons(all_rows)
    weighted_rows = weighted_rank(avg_rows, weights, args.strict, profit_scenarios)
    # prepare lookup for gates using avg rows
    avg_lookup = {}
    for row in avg_rows:
        avg_lookup[(row["config"], row["scenario"], row["grid_levels"])] = {
            "avg_pnl": _safe_float(row.get("avg_pnl", "0")),
            "avg_dd": _safe_float(row.get("avg_dd", "0")),
            "avg_trades": _safe_float(row.get("avg_trades", "0")),
        }
    gate_rows = compute_gates(
        all_rows,
        gate_scenarios,
        args.gate_max_loss_quote,
        args.gate_max_dd_pct,
        avg_lookup,
    )

    avg_path = out_dir / "avg_by_scenario.csv"
    status_path = out_dir / "status_counts.csv"
    stopped_path = out_dir / "stopped_reasons.csv"
    weighted_path = out_dir / "weighted_rank.csv"
    gates_path = out_dir / "gates.csv"

    write_csv(avg_path, avg_rows)
    write_csv(status_path, status_rows)
    write_csv(stopped_path, stopped_rows)
    write_csv(weighted_path, weighted_rows)
    gate_headers = [
        "config",
        "grid_levels",
        "scenario",
        "runs",
        "stopped",
        "inventory_drawdown_runs",
        "trade_runs",
        "avg_pnl",
        "avg_dd_pct",
        "avg_trades",
        "stopped_reasons_top",
        "gate_pass",
    ]
    write_csv(gates_path, gate_rows, headers=gate_headers)

    print(f"Wrote {avg_path}")
    print(f"Wrote {status_path}")
    print(f"Wrote {stopped_path}")
    print(f"Wrote {gates_path}")
    print_top_weighted(weighted_path, weighted_rows)
    if gate_rows:
        summary: Dict[str, Dict[str, int]] = {}
        for row in gate_rows:
            cfg = row["config"]
            gate_pass = row["gate_pass"] == "true"
            bucket = summary.setdefault(cfg, {"pass": 0, "fail": 0})
            if gate_pass:
                bucket["pass"] += 1
            else:
                bucket["fail"] += 1
        print("Gate summary (per config):")
        for cfg, vals in summary.items():
            total = vals["pass"] + vals["fail"]
            print(f"{cfg}: PASS {vals['pass']} / {total} (FAIL {vals['fail']})")


if __name__ == "__main__":
    main()
