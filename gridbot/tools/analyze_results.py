import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


Number = Optional[float]


def _get_float(row: Dict[str, str], keys: Sequence[str]) -> Number:
    for key in keys:
        if key not in row or row[key] in (None, "", "None"):
            continue
        try:
            return float(row[key])
        except (TypeError, ValueError):
            continue
    return None


def _stats(values: List[float]) -> Tuple[int, Number, Number, Number, Number]:
    if not values:
        return 0, None, None, None, None
    values_sorted = sorted(values)
    n = len(values_sorted)
    avg = sum(values_sorted) / n
    if n % 2:
        median = values_sorted[n // 2]
    else:
        median = (values_sorted[n // 2 - 1] + values_sorted[n // 2]) / 2
    return n, avg, median, values_sorted[0], values_sorted[-1]


def _format_stat(value: Number) -> str:
    if value is None:
        return "n/a"
    return f"{value:.6f}"


def _print_global(metrics: Dict[str, List[float]]) -> None:
    print("Global summary")
    print(f"{'metric':15} {'count':>6} {'avg':>12} {'median':>12} {'min':>12} {'max':>12}")
    for key in ["pnl_net", "pnl_gross", "fees", "maker_ratio", "trades", "dd_pct"]:
        n, avg, median, min_v, max_v = _stats(metrics.get(key, []))
        print(
            f"{key:15} {n:6d} {_format_stat(avg):>12} {_format_stat(median):>12} "
            f"{_format_stat(min_v):>12} {_format_stat(max_v):>12}"
        )
    print()


def _safe_avg(values: Iterable[float]) -> Number:
    vals = list(values)
    if not vals:
        return None
    return sum(vals) / len(vals)


def _print_scenarios(groups: Dict[str, List[Dict[str, float]]]) -> None:
    print("Per-scenario summary")
    header = (
        f"{'scenario':15} {'count':>6} {'avg_pnl_net':>12} {'avg_fees':>12} "
        f"{'avg_maker_ratio':>15} {'avg_trades':>12} {'pnl_net_positive%':>18}"
    )
    print(header)
    for scenario, rows in sorted(groups.items()):
        pnl_vals = [r["pnl_net"] for r in rows if r["pnl_net"] is not None]
        fees_vals = [r["fees"] for r in rows if r["fees"] is not None]
        maker_vals = [r["maker_ratio"] for r in rows if r["maker_ratio"] is not None]
        trades_vals = [r["trades"] for r in rows if r["trades"] is not None]
        count = len(rows)
        positive = len([r for r in rows if r["pnl_net"] is not None and r["pnl_net"] > 0])
        pct_positive = (positive / count * 100) if count else None
        print(
            f"{scenario:15} {count:6d} "
            f"{_format_stat(_safe_avg(pnl_vals)):>12} "
            f"{_format_stat(_safe_avg(fees_vals)):>12} "
            f"{_format_stat(_safe_avg(maker_vals)):>15} "
            f"{_format_stat(_safe_avg(trades_vals)):>12} "
            f"{_format_stat(pct_positive):>18}"
        )


def analyze_results(path: Path) -> int:
    csv_path = path / "results.csv"
    if not csv_path.exists():
        print(f"results.csv not found in {path}")
        return 1
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            print(f"results.csv in {path} is empty or missing header")
            return 1
        rows = list(reader)
    if not rows:
        print(f"results.csv in {path} has no data rows")
        return 1

    metrics: Dict[str, List[float]] = defaultdict(list)
    by_scenario: Dict[str, List[Dict[str, float]]] = defaultdict(list)

    for row in rows:
        pnl_net = _get_float(row, ["pnl_net", "pnl"])
        pnl_gross = _get_float(row, ["pnl_gross"])
        fees = _get_float(row, ["total_fees_quote", "fees"])
        maker_ratio = _get_float(row, ["maker_ratio"])
        trades = _get_float(row, ["trades"])
        dd_pct = _get_float(row, ["dd_pct"])
        scenario = row.get("scenario", "unknown") or "unknown"

        if pnl_net is not None:
            metrics["pnl_net"].append(pnl_net)
        if pnl_gross is not None:
            metrics["pnl_gross"].append(pnl_gross)
        if fees is not None:
            metrics["fees"].append(fees)
        if maker_ratio is not None:
            metrics["maker_ratio"].append(maker_ratio)
        if trades is not None:
            metrics["trades"].append(trades)
        if dd_pct is not None:
            metrics["dd_pct"].append(dd_pct)

        by_scenario[scenario].append(
            {
                "pnl_net": pnl_net,
                "fees": fees,
                "maker_ratio": maker_ratio,
                "trades": trades,
            }
        )

    _print_global(metrics)
    _print_scenarios(by_scenario)
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze batch_run results.csv")
    parser.add_argument("--path", required=True, help="Directory containing results.csv")
    args = parser.parse_args(argv)
    path = Path(args.path)
    return analyze_results(path)


if __name__ == "__main__":
    sys.exit(main())
