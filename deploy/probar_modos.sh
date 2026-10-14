#!/usr/bin/env bash
# Prueba los modos de navegador contra Barchart y dice cual funciona desde ESTE servidor.
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ" || exit 1
# shellcheck disable=SC1091
source .venv/bin/activate
mkdir -p logs

probar() {  # $1=nombre  $2..=comando
    local nombre="$1"; shift
    echo ">> Probando: $nombre ..."
    if "$@" > "logs/prueba_${nombre}.log" 2>&1; then
        echo "   OK"; return 0
    else
        echo "   FALLO (ver logs/prueba_${nombre}.log)"; return 1
    fi
}

probar headless env BARCHART_HEADLESS=true python paso1_diagnostico.py
probar xvfb xvfb-run -a --server-args="-screen 0 1366x850x24" env BARCHART_HEADLESS=false python paso1_diagnostico.py
if [ -n "${BARCHART_CDP_URL:-}" ]; then
    probar cdp env BARCHART_CDP_URL="$BARCHART_CDP_URL" python paso1_diagnostico.py
fi

echo
echo "== Detalle de cada prueba =="
for f in logs/prueba_*.log; do
    echo "--- $f"
    grep -E "^HTTP|RESULTADO|Filas:" "$f" || tail -n 3 "$f"
done
echo
echo "Usa el primer modo que salga OK:  BARCHART_MODO=headless|xvfb|cdp ./deploy/ejecutar_diario.sh"
