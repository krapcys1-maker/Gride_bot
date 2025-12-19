from pathlib import Path
import sqlite3

import pytest

from gridbot.app import main


FIXTURE_CONFIG = Path("tests/fixtures/config_small.yaml")


def run_bot(tmp_path, extra_args):
    db_path = tmp_path / "bot.db"
    args = [
        "--config",
        str(FIXTURE_CONFIG),
        "--db-path",
        str(db_path),
    ] + extra_args
    main(args)
    return db_path


def test_range_produces_trades(tmp_path):
    db_path = run_bot(
        tmp_path,
        [
            "--dry-run",
            "--offline",
            "--offline-scenario",
            "range",
            "--seed",
            "1",
            "--max-steps",
            "200",
            "--interval",
            "0",
            "--reset-state",
        ],
    )
    conn = sqlite3.connect(db_path)
    trades = conn.execute("SELECT COUNT(*) FROM trades_history").fetchone()[0]
    active = conn.execute("SELECT COUNT(*) FROM active_orders").fetchone()[0]
    conn.close()
    assert trades > 0
    assert active > 0


def test_restart_does_not_duplicate_orders(tmp_path):
    base_args = [
        "--dry-run",
        "--offline",
        "--offline-scenario",
        "range",
        "--seed",
        "2",
        "--interval",
        "0",
    ]
    db_path = run_bot(tmp_path, ["--max-steps", "50", "--reset-state"] + base_args)
    conn = sqlite3.connect(db_path)
    initial_orders = conn.execute("SELECT COUNT(*) FROM active_orders").fetchone()[0]
    conn.close()

    db_path = run_bot(tmp_path, ["--max-steps", "10"] + base_args)
    conn = sqlite3.connect(db_path)
    after_orders = conn.execute("SELECT COUNT(*) FROM active_orders").fetchone()[0]
    conn.close()

    assert after_orders <= initial_orders


def test_flash_crash_triggers_stop(tmp_path):
    db_path = run_bot(
        tmp_path,
        [
            "--dry-run",
            "--offline",
            "--offline-scenario",
            "flash_crash",
            "--seed",
            "3",
            "--max-steps",
            "200",
            "--interval",
            "0",
            "--reset-state",
        ],
    )
    conn = sqlite3.connect(db_path)
    state_row = conn.execute("SELECT status FROM bot_state WHERE id = 1").fetchone()
    active_orders = conn.execute("SELECT COUNT(*) FROM active_orders").fetchone()[0]
    conn.close()

    assert state_row is not None
    assert state_row[0] == "STOPPED"
    assert active_orders == 0
