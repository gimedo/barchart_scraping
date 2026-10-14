"""
PASO 4 (opcional) - Importa el CSV del scraper anterior (barchart_historico.csv,
17 columnas) a la tabla 'capturas' de SQLite, sin duplicar filas.

    python paso4_importar_capturas.py
    python paso4_importar_capturas.py C:\\dev\\scraping\\barchart_historico.csv
"""
import sys

import db


def main():
    ruta = sys.argv[1] if len(sys.argv) > 1 else "barchart_historico.csv"
    con = db.conectar()
    leidas, nuevas = db.importar_capturas_csv(con, ruta)
    print(f"{leidas} filas leidas, {nuevas} nuevas insertadas en 'capturas'.")


if __name__ == "__main__":
    main()
