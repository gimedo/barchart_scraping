#!/usr/bin/env bash
# Deja un Chrome abierto como "servicio interno" sobre una pantalla virtual, con un perfil
# persistente (las cookies del anti-bot se conservan entre ejecuciones).
# Escucha SOLO en 127.0.0.1:9222. Nunca expongas ese puerto a la red.
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ" || exit 1
# shellcheck disable=SC1091
source .venv/bin/activate
CHROME="$(python - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    print(p.chromium.executable_path)
PY
)"
PERFIL="${BARCHART_PERFIL:-$RAIZ/chrome-perfil}"
mkdir -p "$PERFIL"
# Si ejecutas como root, agrega CHROME_EXTRA_ARGS="--no-sandbox" (mejor: usa un usuario normal)
exec xvfb-run -a --server-args="-screen 0 1366x850x24" "$CHROME" \
    --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 \
    --user-data-dir="$PERFIL" --no-first-run --no-default-browser-check \
    --window-size=1366,850 ${CHROME_EXTRA_ARGS:-} about:blank
