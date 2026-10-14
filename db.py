"""SQLite: historial diario por contrato y capturas diarias (formato de 17 columnas)."""
import sqlite3
from datetime import datetime

import pandas as pd

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS historico_diario (
    symbol TEXT NOT NULL,
    fecha TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    change REAL, pct_change REAL,
    volume REAL, open_interest REAL,
    obtenido_en TEXT,
    PRIMARY KEY (symbol, fecha)
);
CREATE TABLE IF NOT EXISTS capturas (
    symbol TEXT NOT NULL,
    last_price REAL, price_change REAL, open_price REAL, high_price REAL,
    low_price REAL, previous_price REAL, volume REAL, open_interest REAL,
    fecha_reporte TEXT,
    fecha_hora_obtencion TEXT NOT NULL,
    mes_anio TEXT, contract TEXT, contract_month TEXT, contract_year TEXT,
    mes_adelante INTEGER, mes TEXT,
    PRIMARY KEY (symbol, fecha_hora_obtencion)
);
"""

COLS_CAPTURAS = [
    "symbol", "last_price", "price_change", "open_price", "high_price",
    "low_price", "previous_price", "volume", "open_interest", "fecha_reporte",
    "fecha_hora_obtencion", "mes_anio", "contract", "contract_month",
    "contract_year", "mes_adelante", "mes",
]


def conectar(path=None):
    con = sqlite3.connect(path or config.DB_PATH)
    con.executescript(SCHEMA)
    return con


def guardar_historico(con, filas):
    """Inserta o reemplaza filas diarias (idempotente). Devuelve cuantas se escribieron."""
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    datos = [
        (f["symbol"], f["fecha"], f["open"], f["high"], f["low"], f["close"],
         f["change"], f["pct_change"], f["volume"], f["open_interest"], ahora)
        for f in filas
    ]
    con.executemany(
        "INSERT OR REPLACE INTO historico_diario VALUES (?,?,?,?,?,?,?,?,?,?,?)", datos
    )
    con.commit()
    return len(datos)


def ultima_fecha(con, symbol):
    return con.execute("SELECT MAX(fecha) FROM historico_diario WHERE symbol=?", (symbol,)).fetchone()[0]


def eliminar_posteriores(con, fecha_iso):
    """Borra filas con fecha posterior al corte (parciales guardadas en corridas anteriores)."""
    n = con.execute("DELETE FROM historico_diario WHERE fecha > ?", (fecha_iso,)).rowcount
    con.commit()
    return n


def importar_capturas_csv(con, ruta_csv):
    """Carga barchart_historico.csv (salida del scraper anterior) en la tabla capturas."""
    df = pd.read_csv(
        ruta_csv,
        dtype={"contract_year": str, "contract_month": str, "contract": str,
               "mes": str, "mes_anio": str, "symbol": str},
    )
    df = df[COLS_CAPTURAS]
    antes = con.execute("SELECT COUNT(*) FROM capturas").fetchone()[0]
    con.executemany(
        f"INSERT OR IGNORE INTO capturas VALUES ({','.join('?' * len(COLS_CAPTURAS))})",
        df.where(pd.notna(df), None).values.tolist(),
    )
    con.commit()
    despues = con.execute("SELECT COUNT(*) FROM capturas").fetchone()[0]
    return len(df), despues - antes
