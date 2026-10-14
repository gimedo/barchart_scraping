"""
PASO 3 - Consultas sobre lo guardado (base del futuro asistente).

    python paso3_consulta.py resumen
    python paso3_consulta.py precio CLX26 2026-09-15
    python paso3_consulta.py rango CLX26 2026-09-01 2026-10-07
    python paso3_consulta.py variacion CLX26 30
"""
import argparse
import sys

import pandas as pd

import db


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("resumen")
    p = sub.add_parser("precio"); p.add_argument("symbol"); p.add_argument("fecha")
    r = sub.add_parser("rango"); r.add_argument("symbol"); r.add_argument("desde"); r.add_argument("hasta")
    v = sub.add_parser("variacion"); v.add_argument("symbol"); v.add_argument("dias", type=int)
    a = ap.parse_args()

    con = db.conectar()
    pd.set_option("display.width", 200)

    if a.cmd == "resumen":
        h = pd.read_sql("""SELECT symbol, COUNT(*) filas, MIN(fecha) desde, MAX(fecha) hasta
                           FROM historico_diario GROUP BY symbol ORDER BY symbol""", con)
        c = pd.read_sql("""SELECT contract raiz, COUNT(DISTINCT fecha_reporte) dias_capturados,
                           COUNT(*) filas FROM capturas GROUP BY contract""", con)
        print("== historico_diario ==\n", h.to_string(index=False) if len(h) else "(vacio)")
        print("\n== capturas (formato 17 columnas) ==\n", c.to_string(index=False) if len(c) else "(vacio)")

    elif a.cmd == "precio":
        d = pd.read_sql("SELECT * FROM historico_diario WHERE symbol=? AND fecha=?",
                        con, params=(a.symbol, a.fecha))
        print(d.to_string(index=False) if len(d) else "Sin dato para esa fecha (fin de semana o feriado?).")

    elif a.cmd == "rango":
        d = pd.read_sql("""SELECT fecha, open, high, low, close, change, volume, open_interest
                           FROM historico_diario WHERE symbol=? AND fecha BETWEEN ? AND ?
                           ORDER BY fecha""", con, params=(a.symbol, a.desde, a.hasta))
        print(d.to_string(index=False) if len(d) else "Sin datos en ese rango.")

    elif a.cmd == "variacion":
        d = pd.read_sql("SELECT fecha, close FROM historico_diario WHERE symbol=? ORDER BY fecha",
                        con, params=(a.symbol,))
        if len(d) < 2:
            print("No hay suficiente historial."); return 1
        d["fecha"] = pd.to_datetime(d["fecha"])
        ult = d.iloc[-1]
        objetivo = ult["fecha"] - pd.Timedelta(days=a.dias)
        previo = d[d["fecha"] <= objetivo]
        if previo.empty:
            print(f"El historial no llega {a.dias} dias atras (desde {d['fecha'].min().date()})."); return 1
        ref = previo.iloc[-1]
        dif = ult["close"] - ref["close"]
        print(f"{a.symbol}: {ref['close']:.4f} ({ref['fecha'].date()}) -> "
              f"{ult['close']:.4f} ({ult['fecha'].date()})  |  {dif:+.4f}  ({dif / ref['close'] * 100:+.2f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
