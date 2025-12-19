import argparse

from gridbot.core.bot import GridBot


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
        "--offline",
        action="store_true",
        help="Offline mode: no exchange connection, use local price feed",
    )
    parser.add_argument(
        "--offline-scenario",
        choices=["range", "trend_up", "trend_down", "flash_crash"],
        help="Generate synthetic offline price feed if CSV/config feed unavailable",
    )
    parser.add_argument(
        "--offline-once",
        action="store_true",
        help="Do not loop offline feed; exit when prices are exhausted",
    )
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    offline_mode = args.offline or bool(args.offline_scenario)
    forced_dry_run = args.dry_run or offline_mode
    bot = (
        GridBot(
            dry_run=True,
            offline=offline_mode,
            offline_scenario=args.offline_scenario,
            offline_once=args.offline_once,
        )
        if forced_dry_run
        else GridBot(
            offline=offline_mode,
            offline_scenario=args.offline_scenario,
            offline_once=args.offline_once,
        )
    )
    try:
        if args.reset_state:
            bot.reset_state()
        bot.run(interval=args.interval)
    except KeyboardInterrupt:
        print("[INFO] Shutdown requested")
        try:
            bot.mark_stopped()
        except Exception:
            pass
    finally:
        bot.close()


if __name__ == "__main__":
    main()
