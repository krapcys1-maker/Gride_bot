import json
from pathlib import Path

from gridbot.tools import batch_run


def test_summary_includes_non_error_runs(monkeypatch, capsys, tmp_path):
    # prepare synthetic results
    fake_results = [
        {"run_id": "r1", "scenario": "s", "seed": 1, "status": "STOPPED", "reason": "panic", "pnl": -1, "dd_pct": 5, "trades": 1},
        {"run_id": "r2", "scenario": "s", "seed": 2, "status": "STOPPED", "reason": "panic", "pnl": -2, "dd_pct": 3, "trades": 2},
        {"run_id": "r3", "scenario": "s", "seed": 3, "status": "COMPLETED", "reason": "", "pnl": 1, "dd_pct": 1, "trades": 3},
        {"run_id": "r4", "scenario": "s", "seed": 4, "status": "ERROR", "reason": "fail", "pnl": None, "dd_pct": None, "trades": 0},
    ]

    csv_path = tmp_path / "results.csv"

    # monkeypatch to skip actual writing and reuse summary logic
    def fake_run(*args, **kwargs):
        return fake_results

    monkeypatch.setattr(batch_run, "run_once", lambda *a, **k: fake_results.pop(0))

    # invoke main_cli with minimal args; it will consume the fake results above
    args = [
        "--out-dir",
        str(tmp_path),
        "--strategy-ids",
        "a",
        "--scenarios",
        "b",
        "--seeds",
        "1,2,3,4",
        "--steps",
        "1",
        "--config",
        "tests/fixtures/config_small.yaml",
    ]
    batch_run.main_cli(args)
    captured = capsys.readouterr().out
    assert "No successful runs" not in captured
    assert "TOP PnL:" in captured
    assert csv_path.exists()
    rows = csv_path.read_text().strip().splitlines()
    assert len(rows) == 1 + 4  # header + 4 rows
