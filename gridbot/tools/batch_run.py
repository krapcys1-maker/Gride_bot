import argparse
import csv
import json
import logging
from pathlib import Path
from typing import List, Optional

from gridbot.app import main


def parse_list(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def ensure_report(report_path: Path, report: dict) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))


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
) -> dict:
    run_id = f"{strategy_id}_{scenario}_seed{seed}"
    db_path = out_dir / "db" / f"{run_id}.db"
    report_path = out_dir / "reports" / f"{run_id}.json"
    args = [
        "--config",
        str(config),
        "--db-path",
        str(db_path),
        "--dry-run",
        "--offline",
        "--offline-scenario",
        scenario,
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
        "status": report.get("status"),
        "reason": report.get("reason"),
        "error_type": report.get("error_type", ""),
        "error_message": report.get("error_message", ""),
        "final_equity": metrics.get("equity"),
        "pnl": metrics.get("pnl"),
        "dd_pct": metrics.get("drawdown_pct"),
        "trades": metrics.get("trades"),
        "fees": metrics.get("total_fees"),
        "start_ts": report.get("start"),
        "end_ts": report.get("end"),
        "report_path": str(report_path),
    }


def main_cli(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Batch run offline simulations")
    parser.add_argument("--out-dir", default="out_runs/", help="Output directory for reports and DBs")
    parser.add_argument("--strategy-ids", default="classic_grid", help="Comma-separated strategy ids")
    parser.add_argument(
        "--scenarios", default="range,trend_up,trend_down,flash_crash", help="Comma-separated offline scenarios"
    )
    parser.add_argument("--seeds", default="1,2,3,4,5", help="Comma-separated seeds")
    parser.add_argument("--steps", type=int, default=500, help="Max steps per run")
    parser.add_argument("--config", default="tests/fixtures/config_small.yaml", help="Path to config file")
    parser.add_argument("--interval", type=float, default=0.0, help="Interval between ticks")
    parser.add_argument("--log-level", default="WARNING", help="Log level for sub-runs")
    parser.add_argument("--parallel", type=int, default=1, help="Parallel workers (>=1, currently sequential)")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on first error")

    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    db_dir = out_dir / "db"
    reports_dir = out_dir / "reports"
    for path in [db_dir, reports_dir]:
        path.mkdir(parents=True, exist_ok=True)

    config_path = Path(args.config)
    strategy_ids = parse_list(args.strategy_ids)
    scenarios = parse_list(args.scenarios)
    seeds = [int(s) for s in parse_list(args.seeds)]

    results: List[dict] = []
    for strategy in strategy_ids:
        for scenario in scenarios:
            for seed in seeds:
                logging.getLogger(__name__).info(f"Running {strategy}/{scenario}/seed{seed}")
                res = run_once(out_dir, config_path, strategy, scenario, seed, args.steps, args.interval, args.log_level)
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
        "status",
        "reason",
        "error_type",
        "error_message",
        "final_equity",
        "pnl",
        "dd_pct",
        "trades",
        "fees",
        "start_ts",
        "end_ts",
        "report_path",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(row)

    top_pnl = sorted([r for r in results if r.get("pnl") is not None], key=lambda x: x["pnl"], reverse=True)[:10]
    top_dd = sorted(
        [r for r in results if r.get("dd_pct") is not None],
        key=lambda x: x["dd_pct"],
    )[:10]

    print("TOP PnL:")
    for r in top_pnl:
        print(f"{r['run_id']}: pnl={r['pnl']} dd={r.get('dd_pct')}")

    print("TOP Low DD:")
    for r in top_dd:
        print(f"{r['run_id']}: dd={r.get('dd_pct')} pnl={r.get('pnl')}")


if __name__ == "__main__":
    main_cli()
