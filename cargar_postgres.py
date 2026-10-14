"""
Carga cotizaciones de futuros en la tabla Postgres de 17 columnas.

FUENTES
  --fuente csv        (por defecto) CSV del scraper diario (barchart_ultima.csv o
                      barchart_historico.csv), que ya trae las 17 columnas.
  --fuente historico  Historial diario de SQLite (paso 2 con Scrapling). Se convierte
                      al formato de 17 columnas: last_price=cierre, previous_price=
                      cierre-cambio, fecha_reporte=fecha, fecha_hora_obtencion=NULL
                      (asi se distinguen las filas rellenadas de las capturas en vivo).

SEGURIDAD (tabla de produccion)
  * Por defecto es una SIMULACION: hace todo dentro de una transaccion y la revierte,
    mostrando cuantas filas serian nuevas y cuantas ya existen. Solo escribe con --insertar.
  * Clave de duplicado: (symbol, fecha_reporte).
  * Modo normal: omite lo que ya existe (no modifica ni borra datos previos).
    Con --reemplazar borra y vuelve a insertar solo las filas con la misma clave.

USO
    python cargar_postgres.py                                   # simulacion con barchart_ultima.csv
    python cargar_postgres.py --insertar
    python cargar_postgres.py --archivo C:\\dev\\scraping\\barchart_historico.csv --insertar
    python cargar_postgres.py --fuente historico --insertar
    python cargar_postgres.py --crear-tabla --insertar          # solo si la tabla NO existe
"""
import argparse
import sys
from datetime import date, datetime

import pandas as pd

import db
import formato17 as f17
import pg_config

TIPOS_CREAR = {
    "symbol": "text NOT NULL", "last_price": "numeric", "price_change": "numeric",
    "open_price": "numeric", "high_price": "numeric", "low_price": "numeric",
    "previous_price": "numeric", "volume": "numeric", "open_interest": "numeric",
    "fecha_reporte": "date NOT NULL", "fecha_hora_obtencion": "timestamp",
    "mes_anio": "text", "contract": "text", "contract_month": "text",
    "contract_year": "text", "mes_adelante": "integer", "mes": "text",
}
# Tipos de la tabla temporal de trabajo (independientes de los de la tabla destino)
TIPOS_TEMP = {k: v.replace(" NOT NULL", "") for k, v in TIPOS_CREAR.items()}


# ------------------------------------------------------------------ lectura
def _nan_a_none(v):
    return None if v is None or (isinstance(v, float) and v != v) or v is pd.NaT else v


def filas_desde_csv(ruta):
    df = pd.read_csv(ruta, dtype={c: str for c in (
        "symbol", "mes_anio", "contract", "contract_month", "contract_year", "mes",
        "fecha_reporte", "fecha_hora_obtencion")})
    faltan = [c for c in f17.COLUMNAS if c not in df.columns]
    if faltan:
        raise SystemExit(f"El CSV no tiene las columnas: {faltan}")
    filas = []
    for r in df[f17.COLUMNAS].to_dict("records"):
        r = {k: _nan_a_none(v) for k, v in r.items()}
        r["fecha_reporte"] = pd.to_datetime(r["fecha_reporte"]).date() if r["fecha_reporte"] else None
        r["fecha_hora_obtencion"] = (pd.to_datetime(r["fecha_hora_obtencion"]).to_pydatetime()
                                     if r["fecha_hora_obtencion"] else None)
        r["mes_adelante"] = int(r["mes_adelante"]) if r["mes_adelante"] is not None else None
        filas.append(r)
    return filas


def filas_desde_historico():
    con = db.conectar()
    df = pd.read_sql("SELECT * FROM historico_diario ORDER BY fecha, symbol", con)
    filas = []
    for r in df.to_dict("records"):
        r = {k: _nan_a_none(v) for k, v in r.items()}
        fecha = datetime.strptime(r["fecha"], "%Y-%m-%d").date()
        deriv = f17.campos_derivados(r["symbol"], fecha)
        if deriv is None:
            continue
        cambio = r["change"]
        filas.append({
            "symbol": r["symbol"], "last_price": r["close"], "price_change": cambio,
            "open_price": r["open"], "high_price": r["high"], "low_price": r["low"],
            "previous_price": round(r["close"] - cambio, 6) if cambio is not None else None,
            "volume": r["volume"], "open_interest": r["open_interest"],
            "fecha_reporte": fecha, "fecha_hora_obtencion": None, **deriv,
        })
    return filas


# ------------------------------------------------------------------ postgres
def columnas_tabla(cur, tabla):
    cur.execute("SELECT to_regclass(%s)", (tabla,))
    if cur.fetchone()[0] is None:
        return None
    cur.execute("""SELECT a.attname, format_type(a.atttypid, a.atttypmod)
                   FROM pg_attribute a
                   WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped
                   ORDER BY a.attnum""", (tabla,))
    return dict(cur.fetchall())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fuente", choices=["csv", "historico"], default="csv")
    ap.add_argument("--archivo", default="barchart_ultima.csv", help="CSV de origen (fuente csv)")
    ap.add_argument("--tabla", default=None, help="tabla destino (si no, PG_TABLE del .env)")
    ap.add_argument("--insertar", action="store_true", help="escribir de verdad (si no, simulacion)")
    ap.add_argument("--reemplazar", action="store_true",
                    help="reemplazar filas con la misma clave (symbol, fecha_reporte)")
    ap.add_argument("--crear-tabla", action="store_true", help="crear la tabla si no existe")
    a = ap.parse_args()

    tabla = a.tabla or pg_config.tabla()
    if not tabla:
        raise SystemExit("Falta el nombre de la tabla: define PG_TABLE en .env o usa --tabla.")
    p = pg_config.parametros()
    if not p["user"]:
        raise SystemExit("Falta PGUSER (y PGPASSWORD) en .env. Copia .env.example a .env.")

    filas = filas_desde_csv(a.archivo) if a.fuente == "csv" else filas_desde_historico()
    # quitar sin clave y duplicados dentro del propio lote (gana la ultima)
    unicas = {}
    for r in filas:
        if r["symbol"] and r["fecha_reporte"]:
            unicas[(r["symbol"], r["fecha_reporte"])] = r
    filas = list(unicas.values())
    if not filas:
        raise SystemExit("No hay filas para cargar.")
    fechas = [r["fecha_reporte"] for r in filas]
    print(f"Origen: {a.fuente} | {len(filas):,} filas | fecha_reporte {min(fechas)} -> {max(fechas)}")

    import psycopg2
    from psycopg2.extras import execute_values

    print(f"Conectando a {p['host']}:{p['port']}/{p['dbname']} como {p['user']} ...")
    con = psycopg2.connect(connect_timeout=15, **p)
    try:
        cur = con.cursor()
        cols = columnas_tabla(cur, tabla)
        if cols is None:
            if not a.crear_tabla:
                raise SystemExit(f"La tabla {tabla!r} no existe. Revisa PG_TABLE o usa --crear-tabla.")
            ddl = ", ".join(f"{c} {TIPOS_CREAR[c]}" for c in f17.COLUMNAS)
            cur.execute(f"CREATE TABLE {tabla} ({ddl})")
            cur.execute(f"CREATE UNIQUE INDEX ON {tabla} (symbol, fecha_reporte)")
            print(f"Tabla {tabla} creada (con indice unico symbol+fecha_reporte).")
            cols = columnas_tabla(cur, tabla)
        faltan = [c for c in f17.COLUMNAS if c not in cols]
        if faltan:
            raise SystemExit(f"A la tabla le faltan columnas: {faltan}")
        extra = [c for c in cols if c not in f17.COLUMNAS]
        if extra:
            print(f"Aviso: la tabla tiene columnas extra (se dejan con su valor por defecto): {extra}")
        print("Tipos en destino: " + ", ".join(
            f"{c}={cols[c]}" for c in ("fecha_reporte", "fecha_hora_obtencion", "contract_year", "mes_adelante")))

        # tabla temporal de trabajo
        cur.execute("CREATE TEMP TABLE _nuevos (%s) ON COMMIT DROP" %
                    ", ".join(f"{c} {TIPOS_TEMP[c]}" for c in f17.COLUMNAS))
        execute_values(cur, f"INSERT INTO _nuevos ({', '.join(f17.COLUMNAS)}) VALUES %s",
                       [tuple(r[c] for c in f17.COLUMNAS) for r in filas], page_size=2000)

        existe = ("EXISTS (SELECT 1 FROM {t} t WHERE t.symbol = n.symbol "
                  "AND t.fecha_reporte::date = n.fecha_reporte)").format(t=tabla)
        cur.execute(f"SELECT count(*) FROM _nuevos n WHERE {existe}")
        ya = cur.fetchone()[0]
        nuevas = len(filas) - ya
        print(f"\nYa existen en la tabla: {ya:,} | nuevas: {nuevas:,}")

        lista = ", ".join(f17.COLUMNAS)
        if a.reemplazar:
            cur.execute(f"DELETE FROM {tabla} t USING _nuevos n WHERE t.symbol = n.symbol "
                        "AND t.fecha_reporte::date = n.fecha_reporte")
            borradas = cur.rowcount
            cur.execute(f"INSERT INTO {tabla} ({lista}) SELECT {lista} FROM _nuevos")
            insertadas = cur.rowcount
            resumen = f"{borradas:,} reemplazadas, {insertadas:,} insertadas"
        else:
            cur.execute(f"INSERT INTO {tabla} ({lista}) SELECT {lista} FROM _nuevos n WHERE NOT {existe}")
            insertadas = cur.rowcount
            resumen = f"{insertadas:,} insertadas, {ya:,} omitidas por existir"

        if a.insertar:
            con.commit()
            print(f"\nLISTO (escrito en {tabla}): {resumen}")
        else:
            con.rollback()
            print(f"\nSIMULACION (no se escribio nada): se tendria {resumen}")
            print("Para escribir de verdad agrega --insertar")
    except SystemExit:
        con.rollback()
        raise
    except Exception as e:
        con.rollback()
        print(f"ERROR, se revirtio todo: {e}", file=sys.stderr)
        return 1
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
