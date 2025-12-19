import sqlite3
from pathlib import Path

from gridbot.app import main


def test_range_generates_trades(tmp_path):
    cfg_src = Path("tests/fixtures/config_batch.yaml")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(cfg_src.read_text())
    db_path = tmp_path / "bot.db"
    args = [
        "--config",
        str(cfg),
        "--db-path",
        str(db_path),
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
    ]
    main(args)
    conn = sqlite3.connect(db_path)
    trades = conn.execute("SELECT COUNT(*) FROM trades_history").fetchone()[0]
    state = conn.execute("SELECT status FROM bot_state WHERE id=1").fetchone()
    conn.close()
    assert trades >= 10
    assert state and state[0] in ("COMPLETED", "RUNNING", "OK")
