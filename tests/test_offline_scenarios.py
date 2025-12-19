import sqlite3
from pathlib import Path

import pytest
import yaml

from gridbot.app import main


FIXTURE_CONFIG = Path("tests/fixtures/config_small.yaml")


def write_config(tmp_path, overrides=None):
    base = yaml.safe_load(FIXTURE_CONFIG.read_text())
    overrides = overrides or {}

    def merge(dst, src):
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                merge(dst[k], v)
            else:
                dst[k] = v

    merge(base, overrides)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(base))
    return cfg_path


def run_bot(tmp_path, extra_args, overrides=None):
    cfg_path = write_config(tmp_path, overrides)
    db_path = tmp_path / "bot.db"
    args = [
        "--config",
        str(cfg_path),
        "--db-path",
        str(db_path),
    ] + extra_args
    main(args)
    return db_path


def test_range_produces_trades(tmp_path):
    overrides = {
        "accounting": {
            "initial_usdt": 5000.0,
            "initial_base": 0.01,
        }
    }
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
        overrides=overrides,
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


def test_price_jump_pauses_then_resumes(tmp_path, monkeypatch):
    class Feed:
        def __init__(self) -> None:
            self.reset()

        def reset(self) -> None:
            self.values = [88000.0, 91000.0, 91000.0]
            self.idx = 0

        def __call__(self, _self_bot):
            if self.idx >= len(self.values):
                return self.values[-1]
            value = self.values[self.idx]
            self.idx += 1
            return value

    feed = Feed()
    monkeypatch.setattr("gridbot.core.bot.GridBot.fetch_current_price", lambda self: feed(self))

    overrides = {
        "risk": {
            "max_price_jump_pct": 0.5,
            "pause_seconds": 5,
        },
    }
    db_path = run_bot(
        tmp_path,
        [
            "--dry-run",
            "--offline",
            "--max-steps",
            "1",
            "--interval",
            "0",
            "--reset-state",
        ],
        overrides=overrides,
    )
    conn = sqlite3.connect(db_path)
    status1 = conn.execute("SELECT status, reason FROM bot_state WHERE id = 1").fetchone()
    conn.close()
    assert status1[0] == "PAUSED"
    assert status1[1] == "price_jump"

    feed.reset()
    db_path = run_bot(
        tmp_path,
        [
            "--dry-run",
            "--offline",
            "--max-steps",
            "2",
            "--interval",
            "0",
        ],
        overrides=overrides,
    )
    conn = sqlite3.connect(db_path)
    status2 = conn.execute("SELECT status FROM bot_state WHERE id = 1").fetchone()
    conn.close()
    assert status2[0] == "RUNNING"


def test_too_many_errors_stops_and_clears(tmp_path, monkeypatch):
    overrides = {
        "risk": {
            "max_consecutive_errors": 2,
            "max_price_jump_pct": 100.0,
            "pause_seconds": 0,
        },
    }

    # feed returns some prices then raises to trigger errors
    prices = iter([88000, 88100])

    def faulty_feed(self):
        try:
            return next(prices)
        except StopIteration:
            raise RuntimeError("feed failure")

    monkeypatch.setattr("gridbot.core.bot.GridBot._next_offline_price", faulty_feed)

    db_path = run_bot(
        tmp_path,
        [
            "--dry-run",
            "--offline",
            "--offline-once",
            "--max-steps",
            "5",
            "--interval",
            "0",
            "--reset-state",
        ],
        overrides=overrides,
    )
    conn = sqlite3.connect(db_path)
    status_row = conn.execute("SELECT status, reason FROM bot_state WHERE id = 1").fetchone()
    active_orders = conn.execute("SELECT COUNT(*) FROM active_orders").fetchone()[0]
    conn.close()

    assert status_row[0] == "STOPPED"
    assert status_row[1] == "too_many_errors"
    assert active_orders == 0


def test_trend_down_drawdown_stops(tmp_path):
    overrides = {
        "accounting": {
            "enabled": True,
            "initial_usdt": 0.0,
            "initial_base": 0.02,
        },
        "risk": {
            "max_drawdown_pct": 1.0,
            "max_price_jump_pct": 100.0,
        },
    }
    db_path = run_bot(
        tmp_path,
        [
            "--dry-run",
            "--offline",
            "--offline-scenario",
            "trend_down",
            "--seed",
            "4",
            "--max-steps",
            "300",
            "--interval",
            "0",
            "--reset-state",
        ],
        overrides=overrides,
    )
    conn = sqlite3.connect(db_path)
    status_row = conn.execute("SELECT status, reason FROM bot_state WHERE id = 1").fetchone()
    conn.close()
    assert status_row[0] == "STOPPED"
    assert status_row[1] == "max_drawdown"
