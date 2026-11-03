#!/usr/bin/env bash
# Генерирует примеры карточек для двух товаров из examples/ в examples/out/.
# Нужен ключ: переменная ANTHROPIC_API_KEY или файл .env в корне проекта.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=.venv/bin/python
[ -x "$PY" ] || PY=python3

"$PY" -m card_gen \
  examples/manometer_tm510r_m2.json \
  examples/gas_detector_dz1_co.json \
  --out-dir examples/out "$@"
