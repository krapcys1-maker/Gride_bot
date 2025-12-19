import argparse
import logging
from pathlib import Path
from typing import Optional, Sequence

from gridbot.core.bot import GridBot


def configure_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    lvl = getattr(logging, level.upper(), logging.INFO)
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GridBot runner")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run mode regardless of config")
    parser.add_argument(
        "--reset-state",
        action="store_true",
        help="Clear active orders and bot state in SQLite before starting",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="Sleep interval between price checks (seconds, default: 10)",
    )
    parser.add_argument(
        "--status-every-seconds",
        type=float,
        default=10.0,
        help="Log heartbeat (price/status) at most once per given seconds (default: 10)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Offline mode: no exchange connection, use local price feed",
    )
    parser.add_argument(
        "--offline-scenario",
        choices=["range", "trend_up", "trend_down", "flash_crash", "from_csv_ohlc"],
        help="Generate synthetic offline price feed if CSV/config feed unavailable",
    )
    parser.add_argument(
        "--offline-once",
        action="store_true",
        help="Do not loop offline feed; exit when prices are exhausted",
    )
    parser.add_argument(
        "--offline-csv",
        help="Path to CSV with OHLC data for offline mode",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        help="Limit main loop iterations for testing; exits cleanly after N steps",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to config.yaml (default: config.yaml)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        help="Path to SQLite db file (default: grid_bot.db)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Seed for deterministic offline scenarios",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARN, ERROR)",
    )
    parser.add_argument(
        "--log-file",
        help="Optional log file path (in addition to console)",
    )
    parser.add_argument(
        "--report-json",
        help="Optional path to write final run report JSON",
    )
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    configure_logging(args.log_level, args.log_file)
    logger = logging.getLogger(__name__)
    offline_mode = args.offline or bool(args.offline_scenario)
    forced_dry_run = args.dry_run or offline_mode
    bot = (
        GridBot(
            dry_run=True,
            offline=offline_mode,
            offline_scenario=args.offline_scenario,
            offline_once=args.offline_once,
            offline_csv=args.offline_csv,
            config_path=args.config,
            db_path=args.db_path,
            seed=args.seed,
            status_every_seconds=args.status_every_seconds,
            report_path=args.report_json,
        )
        if forced_dry_run
        else GridBot(
            offline=offline_mode,
            offline_scenario=args.offline_scenario,
            offline_once=args.offline_once,
            offline_csv=args.offline_csv,
            config_path=args.config,
            db_path=args.db_path,
            seed=args.seed,
            status_every_seconds=args.status_every_seconds,
            report_path=args.report_json,
        )
    )
    try:
        if args.reset_state:
            bot.reset_state()
        report = bot.run(interval=args.interval, max_steps=args.max_steps)
        if args.report_json and report:
            import json
            try:
                report_path = Path(args.report_json)
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(json.dumps(report, indent=2))
            except Exception as exc:  # pragma: no cover
                logger.error(f"Nie udalo sie zapisac raportu JSON ({args.report_json}): {exc}")
                raise SystemExit(2)
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
        try:
            bot.mark_stopped()
        except Exception:
            pass
    finally:
        bot.close()


if __name__ == "__main__":
    main()
