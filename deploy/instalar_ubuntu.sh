#!/usr/bin/env bash
# Instalacion en Ubuntu Server (sin interfaz grafica). Ejecutar como usuario normal con sudo.
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"

echo ">> Paquetes del sistema (Python, pantalla virtual Xvfb, fuentes)"
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip xvfb xauth fonts-liberation

echo ">> Entorno virtual y librerias de Python"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ">> Navegadores (Playwright para la captura diaria, Scrapling para el historial)"
playwright install chromium
sudo "$RAIZ/.venv/bin/python" -m playwright install-deps chromium
scrapling install

mkdir -p logs
chmod +x deploy/*.sh
echo
echo "Listo. Siguientes pasos:"
echo "  1) cp .env.example .env && chmod 600 .env && nano .env     (datos de Postgres)"
echo "  2) ./deploy/probar_modos.sh                                (ver que modo pasa el anti-bot)"
