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
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    bot = GridBot(dry_run=True) if args.dry_run else GridBot()
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
