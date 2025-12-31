import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


SCENARIO_ORDER = ["range", "trend_up", "trend_down", "flash_crash"]


def _percentile(values: List[float], percentile: float) -> Optional[float]:
    """Nearest-rank percentile (deterministic, no interpolation)."""
    if not values:
        return None
    if percentile <= 0:
        return min(values)
    if percentile >= 100:
        return max(values)
    values_sorted = sorted(values)
    rank = int(percentile / 100 * len(values_sorted))
    rank = max(1, rank)
    rank = min(rank, len(values_sorted))
    return values_sorted[rank - 1]


def _safe_float(value: str) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _load_results(path: Path) -> List[Dict[str, str]]:
    results_path = path / "results.csv"
    if not results_path.exists():
        raise SystemExit(f"Missing results.csv in {path}")
    with results_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        required = ["scenario", "status", "reason", "pnl", "trades"]
        missing = [c for c in required if c not in fieldnames]
        if missing:
            raise SystemExit(f"{results_path}: missing required columns: {', '.join(missing)}")
        rows = list(reader)
    return rows


def _aggregate(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, Optional[float]]]:
    grouped: Dict[str, Dict[str, any]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        scenario = row.get("scenario") or "unknown"
        grouped[scenario]["rows"].append(row)
    summary: Dict[str, Dict[str, Optional[float]]] = {}
    for scenario, payload in grouped.items():
        rows = payload["rows"]
        n = len(rows)
        status_list = [str(r.get("status") or "").upper() for r in rows]
        reason_counter = Counter()
        stopped_count = 0
        completed_count = 0
        pnl_list: List[float] = []
        dd_list: List[float] = []
        trades_list: List[int] = []
        eff_gl_list: List[int] = []
        for r in rows:
            status = str(r.get("status") or "").upper()
            reason = str(r.get("reason") or "")
            if status == "STOPPED":
                stopped_count += 1
                reason_counter[reason] += 1
            if status == "COMPLETED":
                completed_count += 1
            pnl_val = _safe_float(r.get("pnl"))
            if pnl_val is not None:
                pnl_list.append(pnl_val)
            dd_val = _safe_float(r.get("dd_pct") or r.get("dd"))
            if dd_val is not None:
                dd_list.append(dd_val)
            trades_val = _safe_int(r.get("trades"))
            if trades_val is not None:
                trades_list.append(trades_val)
            gl_eff_val = _safe_int(r.get("grid_levels_effective"))
            if gl_eff_val is not None:
                eff_gl_list.append(gl_eff_val)
        stopped_pct = stopped_count / n if n else None
        pnl_avg = sum(pnl_list) / len(pnl_list) if pnl_list else None
        pnl_p10 = _percentile(pnl_list, 10)
        dd_avg = sum(dd_list) / len(dd_list) if dd_list else None
        dd_p90 = _percentile(dd_list, 90)
        trades_avg = sum(trades_list) / len(trades_list) if trades_list else None
        eff_gl_avg = sum(eff_gl_list) / len(eff_gl_list) if eff_gl_list else None
        reason_top = reason_counter.most_common(1)[0][0] if reason_counter else ""
        summary[scenario] = {
            "scenario": scenario,
            "n": n,
            "stopped_count": stopped_count,
            "stopped_pct": stopped_pct,
            "completed_count": completed_count,
            "pnl_avg": pnl_avg,
            "pnl_p10": pnl_p10,
            "dd_avg": dd_avg,
            "dd_p90": dd_p90,
            "trades_avg": trades_avg,
            "eff_gl_avg": eff_gl_avg,
            "reason_top": reason_top,
        }
    return summary


def _apply_baseline(current: Dict[str, Dict[str, Optional[float]]], baseline: Dict[str, Dict[str, Optional[float]]]) -> None:
    for scenario, metrics in current.items():
        base = baseline.get(scenario)
        if not base:
            metrics.update(
                {
                    "pnl_avg_base": None,
                    "dd_avg_base": None,
                    "pnl_avg_delta_abs": None,
                    "pnl_avg_delta_pct": None,
                    "dd_avg_delta_abs": None,
                    "dd_avg_delta_pct": None,
                }
            )
            continue
        pnl_base = base.get("pnl_avg")
        dd_base = base.get("dd_avg")
        pnl_curr = metrics.get("pnl_avg")
        dd_curr = metrics.get("dd_avg")
        pnl_delta_abs = pnl_curr - pnl_base if pnl_curr is not None and pnl_base is not None else None
        dd_delta_abs = dd_curr - dd_base if dd_curr is not None and dd_base is not None else None
        denom_pnl = max(abs(pnl_base), 1e-9) if pnl_base is not None else None
        denom_dd = max(abs(dd_base), 1e-9) if dd_base is not None else None
        metrics.update(
            {
                "pnl_avg_base": pnl_base,
                "dd_avg_base": dd_base,
                "pnl_avg_delta_abs": pnl_delta_abs,
                "pnl_avg_delta_pct": (pnl_delta_abs / denom_pnl) if pnl_delta_abs is not None and denom_pnl else None,
                "dd_avg_delta_abs": dd_delta_abs,
                "dd_avg_delta_pct": (dd_delta_abs / denom_dd) if dd_delta_abs is not None and denom_dd else None,
            }
        )


def _gate_rules(metrics: Dict[str, Dict[str, Optional[float]]]) -> Tuple[bool, List[str]]:
    failed: List[str] = []
    for scenario, vals in metrics.items():
        n = vals.get("n") or 0
        stopped = vals.get("stopped_count") or 0
        pnl_avg = vals.get("pnl_avg")
        dd_p90 = vals.get("dd_p90")
        reason_top = vals.get("reason_top") or ""
        if scenario == "range":
            if stopped != 0:
                failed.append("range: stopped_count!=0")
            if pnl_avg is None or pnl_avg <= 0:
                failed.append("range: pnl_avg<=0")
        elif scenario == "trend_up":
            if stopped != 0:
                failed.append("trend_up: stopped_count!=0")
            if dd_p90 is None or dd_p90 > 1.0:
                failed.append("trend_up: dd_p90>1.0")
        elif scenario == "trend_down":
            if stopped != 0:
                failed.append("trend_down: stopped_count!=0")
        elif scenario == "flash_crash":
            if n == 0 or stopped != n:
                failed.append("flash_crash: not all runs stopped")
            if reason_top not in {"panic_sell", "max_drawdown", "inventory_drawdown"}:
                failed.append("flash_crash: reason_top not panic/max_dd/inventory_drawdown")
            if dd_p90 is None or dd_p90 > 15.0:
                failed.append("flash_crash: dd_p90>15.0")
    overall_pass = len(failed) == 0
    return overall_pass, failed


def _gate_baseline(metrics: Dict[str, Dict[str, Optional[float]]], failed: List[str]) -> None:
    range_vals = metrics.get("range") or {}
    delta_pnl_pct = range_vals.get("pnl_avg_delta_pct")
    delta_dd_pct = range_vals.get("dd_avg_delta_pct")
    if delta_pnl_pct is not None and delta_pnl_pct < -0.10:
        failed.append("baseline range: pnl_avg worsened >10%")
    if delta_dd_pct is not None and delta_dd_pct > 0.20:
        failed.append("baseline range: dd_avg worsened >20%")


def _order_scenarios(metrics: Dict[str, Dict[str, Optional[float]]]) -> List[Dict[str, Optional[float]]]:
    ordered: List[Dict[str, Optional[float]]] = []
    seen = set()
    for name in SCENARIO_ORDER:
        if name in metrics:
            ordered.append(metrics[name])
            seen.add(name)
    for name in sorted(metrics):
        if name not in seen:
            ordered.append(metrics[name])
    return ordered


def evaluate(out_dir: Path, baseline_dir: Optional[Path] = None) -> Dict[str, any]:
    rows = _load_results(out_dir)
    current_metrics = _aggregate(rows)
    baseline_metrics: Dict[str, Dict[str, Optional[float]]] = {}
    if baseline_dir is not None:
        base_rows = _load_results(baseline_dir)
        baseline_metrics = _aggregate(base_rows)
        _apply_baseline(current_metrics, baseline_metrics)
    overall_pass, failed_rules = _gate_rules(current_metrics)
    if baseline_dir is not None:
        _gate_baseline(current_metrics, failed_rules)
        overall_pass = overall_pass and len(failed_rules) == 0
    ordered = _order_scenarios(current_metrics)
    return {
        "out_dir": str(out_dir),
        "baseline_dir": str(baseline_dir) if baseline_dir else None,
        "scenarios": ordered,
        "overall_pass": overall_pass,
        "failed_rules": failed_rules,
    }


def _format_table(summary: Dict[str, any]) -> str:
    lines: List[str] = []
    header = (
        "scenario n stopped pnl_avg pnl_p10 dd_avg dd_p90 trades_avg eff_gl_avg reason_top pnl_base pnl_delta% dd_base dd_delta%"
    )
    lines.append(header)
    for m in summary["scenarios"]:
        line = (
            f"{m.get('scenario',''):<11}"
            f"{m.get('n',0):>3} "
            f"{m.get('stopped_count',0):>7} "
            f"{(m.get('pnl_avg') if m.get('pnl_avg') is not None else float('nan')):>8.3f} "
            f"{(m.get('pnl_p10') if m.get('pnl_p10') is not None else float('nan')):>8.3f} "
            f"{(m.get('dd_avg') if m.get('dd_avg') is not None else float('nan')):>7.3f} "
            f"{(m.get('dd_p90') if m.get('dd_p90') is not None else float('nan')):>7.3f} "
            f"{(m.get('trades_avg') if m.get('trades_avg') is not None else float('nan')):>10.3f} "
            f"{(m.get('eff_gl_avg') if m.get('eff_gl_avg') is not None else float('nan')):>11.3f} "
            f"{m.get('reason_top','') or '':<12} "
            f"{(m.get('pnl_avg_base') if m.get('pnl_avg_base') is not None else float('nan')):>8.3f} "
            f"{(m.get('pnl_avg_delta_pct') if m.get('pnl_avg_delta_pct') is not None else float('nan')):>10.3f} "
            f"{(m.get('dd_avg_base') if m.get('dd_avg_base') is not None else float('nan')):>8.3f} "
            f"{(m.get('dd_avg_delta_pct') if m.get('dd_avg_delta_pct') is not None else float('nan')):>10.3f}"
        )
        lines.append(line)
    lines.append(f"OVERALL: {'PASS' if summary['overall_pass'] else 'FAIL'}")
    if summary["failed_rules"]:
        lines.append("Failed rules: " + "; ".join(summary["failed_rules"]))
    return "\n".join(lines)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate synthetic scenarios with gates")
    parser.add_argument("--out-dir", required=True, help="Directory with results.csv from batch_run")
    parser.add_argument("--baseline-dir", help="Directory with baseline results.csv")
    parser.add_argument("--format", choices=["table", "json"], default="table", help="Output format (default table)")
    parser.add_argument("--out-json", help="Path to write JSON summary")
    parser.add_argument("--strict", action=argparse.BooleanOptionalAction, default=True, help="Fail with exit code 2 on gate fail (default: true)")
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    baseline_dir = Path(args.baseline_dir) if args.baseline_dir else None
    summary = evaluate(out_dir, baseline_dir)
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(summary, indent=2))
    if args.format == "json":
        print(json.dumps(summary, indent=2))
    else:
        print(_format_table(summary))
    if not summary["overall_pass"] and args.strict:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
