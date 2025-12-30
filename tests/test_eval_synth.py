import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gridbot.tools import eval_synth


def test_eval_pass_summary():
    out_dir = REPO_ROOT / "tests/fixtures/eval/pass"
    summary = eval_synth.evaluate(out_dir)
    assert summary["overall_pass"] is True
    scenarios = {m["scenario"]: m for m in summary["scenarios"]}
    assert scenarios["range"]["stopped_count"] == 0
    assert scenarios["range"]["pnl_avg"] > 0


def test_eval_fail_exit_code():
    out_dir = REPO_ROOT / "tests/fixtures/eval/fail"
    summary = eval_synth.evaluate(out_dir)
    assert summary["overall_pass"] is False
    with pytest.raises(SystemExit) as exc:
        eval_synth.main(["--out-dir", str(out_dir)])
    assert exc.value.code == 2


def test_baseline_deltas():
    out_dir = REPO_ROOT / "tests/fixtures/eval/pass"
    base_dir = REPO_ROOT / "tests/fixtures/eval/pass"
    summary = eval_synth.evaluate(out_dir, base_dir)
    range_metrics = {m["scenario"]: m for m in summary["scenarios"]}["range"]
    assert range_metrics["pnl_avg_delta_abs"] == 0
    assert range_metrics["dd_avg_delta_abs"] == 0
