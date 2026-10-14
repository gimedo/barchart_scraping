@echo off
REM Captura diaria: scraper (Playwright) -> Postgres. Ajusta las dos rutas.
set SCRAPER_DIR=C:\dev\scraping
set PROYECTO_DIR=C:\dev\barchart_scrapling

cd /d %SCRAPER_DIR%
python barchart_scraper.py
if errorlevel 1 (
    echo El scraper fallo. No se carga nada.
    exit /b 1
)

cd /d %PROYECTO_DIR%
python cargar_postgres.py --archivo %SCRAPER_DIR%\barchart_ultima.csv --insertar
