import subprocess
import sys
from pathlib import Path


def test_analyze_results_outputs_stats(tmp_path):
    rows = [
        "run_id,scenario,pnl_net,pnl_gross,total_fees_quote,fees,maker_ratio,trades,dd_pct",
        "r1,range,10.0,12.0,2.0,,1.0,5,1.0",
        "r2,range,8.0,10.0,2.0,,0.5,5,2.0",
        "r3,trend,5.0,7.0,2.0,,0.7,4,3.0",
        "r4,trend,-1.0,1.0,2.5,,0.3,4,4.0",
    ]
    results_path = tmp_path / "results.csv"
    results_path.write_text("\n".join(rows), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "gridbot.tools.analyze_results", "--path", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "range" in out
    assert "trend" in out
    assert "avg_pnl_net" in out
