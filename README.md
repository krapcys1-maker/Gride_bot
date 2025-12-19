# SimpleGrid V1

Minimal grid trading scaffold written in Python. Phase 1 focuses on configuration management and establishing a ccxt connection that can target testnets or sandboxes.

## Getting Started

1. `pip install -r requirements.txt`
2. Review `config.yaml` and substitute your desired trading pair, price range, and allocation per grid line.
3. Run `python grid_bot.py` to verify configuration loads and ccxt connects (testnet/sandbox if enabled).

## Phase 1 Deliverables

- Flat project layout: config, script, and docs in repo root.
- Configuration in `config.yaml`.
- Simple connection code in `grid_bot.py` that validates settings and establishes an exchange client via ccxt.

## Offline / Test Mode

- Set environment variable `GRIDBOT_OFFLINE=1` and ensure `DRY_RUN=true` (e.g., in `config.yaml`).
- Enable `offline: true` and provide a feed via `offline_prices: [100.0, 101.5, 102.0]` or create `data/offline_prices.csv` with one price per line.
- Run with `python main.py` to start without KuCoin API keys.
- CSV feed format: create `data/offline_prices.csv` with one column `price` (header optional), one value per line (e.g., `100.0`).
- Repo zawiera przykladowy `data/offline_prices.csv` (zakres ok. 87500-88500).
- Flaga `--offline-scenario {range,trend_up,trend_down,flash_crash}` wygeneruje syntetyczny feed, gdy brak CSV/config; `--offline-once` zakonczy bota po zuzyciu feedu.

## CLI Examples

- `python main.py`
- `python main.py --dry-run --reset-state`
- `python main.py --dry-run --reset-state --interval 1`
- `python main.py --dry-run --offline --reset-state --interval 1`
- `python main.py --dry-run --offline --offline-scenario trend_up --offline-once`
- `python main.py --dry-run --offline --offline-scenario range --seed 42 --max-steps 200 --reset-state --interval 0`
- `python main.py --dry-run --offline --offline-scenario range --seed 42 --max-steps 200 --reset-state --interval 0 --log-level DEBUG --log-file gridbot.log`
- `pytest -q`
- Batch run example: `python -m gridbot.tools.batch_run --out-dir out_runs --strategy-ids classic_grid --scenarios range --seeds 1,2 --steps 50 --interval 0`
- Repo wymusza LF w plikach tekstowych (patrz .gitattributes); na Windows git auto-konwertuje wg ustawienia core.autocrlf.

## Branching

- `dev`: prace bieżące, gałąź do której trafiają zmiany przed stabilizacją.
- `main`: stabilne wydania.
- PR flow: twórz/aktualizuj zmiany na `dev`, otwieraj PR z `dev` do `main`, po review merguj do `main`.
