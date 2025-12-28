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
- Analyze batch outputs: `python -m gridbot.tools.analyze_results --path out_runs`
- Repo wymusza LF w plikach tekstowych (patrz .gitattributes); na Windows git auto-konwertuje wg ustawienia core.autocrlf.

### Uwagi o initial_base
- W scenariuszu flash_crash z `initial_base > 0` equity spada nawet bez trade'ów (ryzyko trzymania base). Do strojenia mechaniki grid używaj plików `*_nobase.yaml` z `initial_base: 0`.

### Batch 4-scen nobase (PowerShell)
```powershell
# maker100
python -m gridbot.tools.batch_run `
  --out-dir out_4scenarios_maker100_nobase `
  --strategy-ids classic_grid `
  --scenarios range,trend_up,trend_down,flash_crash `
  --seeds 1,2,3,4,5,6,7,8,9,10 `
  --steps 2000 `
  --grid-levels 3,4,5 `
  --config tests/fixtures/config_costs_neutral_maker100_nobase.yaml `
  --interval 0 `
  --log-level WARNING

# mix70
python -m gridbot.tools.batch_run `
  --out-dir out_4scenarios_mix70_nobase `
  --strategy-ids classic_grid `
  --scenarios range,trend_up,trend_down,flash_crash `
  --seeds 1,2,3,4,5,6,7,8,9,10 `
  --steps 2000 `
  --grid-levels 3,4,5 `
  --config tests/fixtures/config_costs_neutral_mix70_nobase.yaml `
  --interval 0 `
  --log-level WARNING

# mix50
python -m gridbot.tools.batch_run `
  --out-dir out_4scenarios_mix50_nobase `
  --strategy-ids classic_grid `
  --scenarios range,trend_up,trend_down,flash_crash `
  --seeds 1,2,3,4,5,6,7,8,9,10 `
  --steps 2000 `
  --grid-levels 3,4,5 `
  --config tests/fixtures/config_costs_neutral_mix50_nobase.yaml `
  --interval 0 `
  --log-level WARNING
```

## Raporty i metryki

- Raport JSON (`--report-json`) zawiera m.in. `pnl_net`, `pnl_gross`, `total_fees_quote`, `spread_cost_est_quote`, `slippage_cost_est_quote`, `maker_ratio`, `avg_fee_per_trade`; pole `pnl` jest aliasem `pnl_net`.
- `gridbot.tools.batch_run` zapisuje powyższe metryki jako kolumny w `results.csv` (legacy kolumny pozostają dla kompatybilności).

## Branching

- `dev`: prace bieżące, gałąź do której trafiają zmiany przed stabilizacją.
- `main`: stabilne wydania.
- PR flow: twórz/aktualizuj zmiany na `dev`, otwieraj PR z `dev` do `main`, po review merguj do `main`.

## Repo hygiene

- Runtime pliki są ignorowane: `out/`, `out_runs/`, `*.db` (w tym `grid_bot.db`), `*.sqlite*`, `trade_history.csv`, `orders.json`, `.env`, cache Pythona.
- Użyj czyszczenia: `powershell -ExecutionPolicy Bypass -File scripts/clean.ps1` lub `bash scripts/clean.sh`.
- Szybka kontrola: `powershell -ExecutionPolicy Bypass -File scripts/check_repo.ps1` (status, tracked outputy, prosty skan tajemnic).

## Safety: hooks

- Zainstaluj lokalny hook blokujący commit wrażliwych plików/sekretów:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\install_hooks.ps1`
