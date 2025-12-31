import csv
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import data_loader  # noqa: E402
from gridbot.app import main  # noqa: E402
import fetch_history as fetch_history_mod  # noqa: E402


class FakeExchange:
    def __init__(self):
        self._calls = 0

    def parse_timeframe(self, tf: str) -> int:
        return 60

    def fetch_ohlcv(self, symbol, timeframe, since, limit):
        self._calls += 1
        if self._calls > 1:
            return []
        return [[since, 1.0, 2.0, 0.5, 1.5, 100]]

    def milliseconds(self) -> int:
        return 0


def test_download_includes_ts_first(monkeypatch, tmp_path):
    monkeypatch.setattr(data_loader, "DATA_DIR", tmp_path)
    monkeypatch.setattr(data_loader.ccxt, "kucoin", lambda *args, **kwargs: FakeExchange())
    out_path = data_loader.download_data("BTC/USDT", start_date="2024-01-01", end_date="2024-01-02")
    rows = list(csv.DictReader(out_path.read_text().splitlines()))
    assert rows
    assert rows[0].get("ts") is not None
    assert rows[0]["open"] == "1.0"
    assert list(rows[0].keys())[:4] == ["ts", "datetime", "open", "high"]


def test_from_csv_ohlc_accepts_ts_column(tmp_path):
    csv_path = tmp_path / "ohlc_ts.csv"
    csv_path.write_text("ts,open,high,low,close\n1,100,110,90,105\n2,105,115,95,110\n")
    data = yaml.safe_load((REPO_ROOT / "tests/fixtures/config_costs_neutral_maker100_nobase.yaml").read_text())
    data["offline"] = True
    data["offline_scenario"] = "from_csv_ohlc"
    data["offline_csv"] = str(csv_path)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(data))
    report_path = tmp_path / "report.json"
    args = [
        "--config",
        str(cfg_path),
        "--db-path",
        str(tmp_path / "bot.db"),
        "--dry-run",
        "--offline",
        "--offline-scenario",
        "from_csv_ohlc",
        "--offline-csv",
        str(csv_path),
        "--seed",
        "1",
        "--max-steps",
        "2",
        "--interval",
        "0",
        "--reset-state",
        "--report-json",
        str(report_path),
        "--log-level",
        "ERROR",
    ]
    main(args)
    assert report_path.exists()


class FakeKucoin:
    def __init__(self):
        self.calls = 0

    def parse_timeframe(self, tf: str) -> int:
        return 60

    def fetch_ohlcv(self, symbol, timeframe, since, limit):
        self.calls += 1
        if self.calls > 1:
            return []
        return [
            [2000, 2.0, 3.0, 1.5, 2.5, 10],
            [1000, 1.0, 2.0, 0.5, 1.5, 20],
            [1000, 1.0, 2.0, 0.5, 1.5, 20],
        ]


def test_fetch_history_exports_ts_and_dedup(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_history_mod, "load_config", lambda: {"symbol": "BTC/USDT"})
    monkeypatch.setattr(fetch_history_mod, "init_exchange", lambda: FakeKucoin())
    out = tmp_path / "out.csv"
    start = fetch_history_mod.datetime(2024, 1, 1, tzinfo=fetch_history_mod.timezone.utc)
    end = fetch_history_mod.datetime(2024, 1, 1, 0, 2, tzinfo=fetch_history_mod.timezone.utc)
    path = fetch_history_mod.fetch_history(start=start, end=end, output_path=out, timeframe="1m")
    rows = list(csv.DictReader(path.read_text().splitlines()))
    keys_lower = [k.lower() for k in rows[0].keys()]
    assert keys_lower[0] == "ts"
    assert "open" in keys_lower and "high" in keys_lower and "low" in keys_lower and "close" in keys_lower
    ts_values = [int(r["ts"]) for r in rows]
    assert ts_values == sorted(ts_values)
    assert len(ts_values) == len(set(ts_values)) == 2
