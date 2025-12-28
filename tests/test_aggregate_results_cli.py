import csv
import json
from pathlib import Path

from gridbot.tools.aggregate_results import main


def _write_results(tmp_path: Path, name: str):
    dir_path = tmp_path / name
    dir_path.mkdir()
    rows = [
        {
            "run_id": "r1",
            "scenario": "flash_crash",
            "grid_levels": "3",
            "status": "STOPPED",
            "reason": "inventory_drawdown",
            "pnl": "0",
            "dd": "0",
            "trades": "0",
        }
    ]
    path = dir_path / "results.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return dir_path


def test_gate_only_mode(tmp_path, capsys):
    in_dir = _write_results(tmp_path, "out_gate")
    out_dir = tmp_path / "agg"
    argv = [
        "--in-dirs",
        str(in_dir),
        "--out-dir",
        str(out_dir),
        "--profit-scenarios",
        "none",
        "--gate-scenarios",
        "flash_crash",
    ]
    main(argv)
    gates_path = out_dir / "gates.csv"
    assert gates_path.exists()
    content = gates_path.read_text().strip().splitlines()
    assert len(content) == 2  # header + one row
    captured = capsys.readouterr().out
    assert "No profitability ranking computed" in captured
