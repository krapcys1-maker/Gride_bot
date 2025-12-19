import json
from pathlib import Path

from gridbot.app import main


def run_report(tmp_path, overrides: dict) -> dict:
    cfg_src = Path("tests/fixtures/config_batch.yaml")
    cfg = tmp_path / "config.yaml"
    base = cfg_src.read_text()
    # crude merge: append overrides yaml fragment
    cfg.write_text(base)
    # apply overrides manually
    text = cfg.read_text()
    import yaml

    data = yaml.safe_load(text)
    for k, v in overrides.items():
        if isinstance(v, dict):
            data.setdefault(k, {}).update(v)
        else:
            data[k] = v
    cfg.write_text(yaml.safe_dump(data))

    db_path = tmp_path / f"bot_{overrides.get('label','')}.db"
    report_path = tmp_path / f"report_{overrides.get('label','')}.json"
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
        "300",
        "--interval",
        "0",
        "--reset-state",
        "--report-json",
        str(report_path),
    ]
    main(args)
    return json.loads(report_path.read_text())


def test_slippage_reduces_pnl(tmp_path):
    base_report = run_report(
        tmp_path,
        {
            "label": "base",
            "accounting": {"spread_bps": 0, "slippage_bps": 0, "maker_fee_bps": 0, "taker_fee_bps": 0},
        },
    )
    worse_report = run_report(
        tmp_path,
        {
            "label": "cost",
            "accounting": {
                "spread_bps": 10,
                "slippage_bps": 20,
                "maker_fee_bps": 20,
                "taker_fee_bps": 20,
            },
        },
    )
    assert base_report["status"] != "ERROR"
    assert worse_report["status"] != "ERROR"
    assert worse_report["metrics"]["pnl_net"] < base_report["metrics"]["pnl_net"]
