#!/usr/bin/env bash
set -euo pipefail

targets=("out" "out_runs" "__pycache__" ".pytest_cache" "*.pyc" "trade_history.csv" "grid_bot.db")

for t in "${targets[@]}"; do
  for path in $t; do
    if [ -e "$path" ]; then
      echo "Removing $path"
      rm -rf "$path"
    fi
  done
done
