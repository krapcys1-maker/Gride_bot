# SimpleGrid V1

Minimal grid trading scaffold written in Python. Phase 1 focuses on configuration management and establishing a ccxt connection that can target testnets or sandboxes.

## Getting Started

1. `pip install -r requirements.txt`
2. Review `config.yaml` and substitute your desired trading pair, price range, and allocation per grid line.
3. Run `python grid_bot.py` to verify configuration loads and ccxt connects (testnet/sandbox if enabled).

## Phase 1 Deliverables

- Flat project layout: config, script, and docs in repo root.
- Configuration in `config.yaml`.
- Simple connection code in `grid_bot.py` that validates settings and establishes an exchange client via ccxt.
