#!/usr/bin/env bash
# Captura diaria: scraper -> Postgres. Pensado para cron.
#   ./deploy/ejecutar_diario.sh                 captura + carga
#   ./deploy/ejecutar_diario.sh --con-historico ademas actualiza el historial de 2 anios
# Modo de navegador:  BARCHART_MODO=xvfb (defecto) | headless | cdp
set -uo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ" || exit 1
# shellcheck disable=SC1091
source .venv/bin/activate
mkdir -p logs
LOG="logs/diario_$(date +%F).log"
exec >>"$LOG" 2>&1

# evita ejecuciones superpuestas
exec 9>/tmp/barchart_diario.lock
flock -n 9 || { echo "$(date '+%F %T') ya hay una ejecucion en curso, se omite"; exit 0; }

MODO="${BARCHART_MODO:-xvfb}"
case "$MODO" in
    xvfb)     ENVOLTORIO=(xvfb-run -a --server-args="-screen 0 1366x850x24" env BARCHART_HEADLESS=false) ;;
    headless) ENVOLTORIO=(env BARCHART_HEADLESS=true) ;;
    cdp)      ENVOLTORIO=(env BARCHART_CDP_URL="${BARCHART_CDP_URL:-http://127.0.0.1:9222}") ;;
    *) echo "BARCHART_MODO invalido: $MODO"; exit 2 ;;
esac

echo "=== $(date '+%F %T') | modo: $MODO ==="

echo "-- 1) Captura diaria (17 columnas)"
( cd captura_diaria && "${ENVOLTORIO[@]}" env BARCHART_EXCEL=false python barchart_scraper.py ) || {
    echo "El scraper fallo; no se carga nada."; exit 1; }

echo "-- 2) Carga a Postgres"
python cargar_postgres.py --archivo captura_diaria/barchart_ultima.csv --insertar || exit 1

if [ "${1:-}" = "--con-historico" ]; then
    echo "-- 3) Historial diario (Scrapling) y carga"
    "${ENVOLTORIO[@]}" python paso2_historico.py || exit 1
    python cargar_postgres.py --fuente historico --insertar || exit 1
fi

echo "=== fin OK $(date '+%F %T') ==="
