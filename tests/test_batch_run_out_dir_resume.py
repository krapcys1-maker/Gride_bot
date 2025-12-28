from gridbot.tools.batch_run import main_cli
import pytest


def _base_args(out_dir):
    return [
        "--out-dir",
        str(out_dir),
        "--strategy-ids",
        "classic_grid",
        "--scenarios",
        "range",
        "--seeds",
        "1",
        "--steps",
        "20",
        "--config",
        "tests/fixtures/config_small.yaml",
        "--interval",
        "0",
        "--log-level",
        "WARNING",
    ]


def test_batch_run_requires_resume_when_out_dir_not_empty(tmp_path):
    out_dir = tmp_path / "out_x"
    args = _base_args(out_dir)
    main_cli(args)

    with pytest.raises(
        SystemExit, match="out-dir already exists with previous results; delete it or run with --resume"
    ):
        main_cli(args)

    main_cli(args + ["--resume"])
