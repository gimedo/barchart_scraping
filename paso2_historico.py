"""
PASO 2 - Descarga el historial diario de cada contrato y lo guarda en SQLite.

Modos:
  --modo pagina  usa lo que la pagina pide sola al cargar (65 sesiones = ~3 meses).
  --modo api     (por defecto) llama al endpoint desde dentro del navegador pidiendo
                 --dias dias (hasta ~730 en cuenta gratuita). Probado: 2 anios.

Los simbolos se generan solos a partir de config.RAICES y config.MESES_ADELANTE.
Mejoras sobre la version anterior:
  * El navegador se abre UNA vez y se reutiliza (antes ~50 s por simbolo).
  * Se descartan las filas parciales (sesion en curso / recien abierta).
  * Los contratos vencidos (sin datos nuevos hace > DIAS_PARA_VENCIDO) se omiten.

Uso:
    python paso2_historico.py
    python paso2_historico.py --simbolos CLX26 HOX26 --dias 730
    python paso2_historico.py --forzar          # reintenta tambien los vencidos
"""
import argparse
import json
import sys
import time
from datetime import date, timedelta

import common
import config
import db


def por_pagina(symbol, sesion):
    url = config.URL_HISTORICO.format(symbol=symbol)
    resp = common.fetch_pagina(url, sesion=sesion)
    mejor = []
    for x in getattr(resp, "captured_xhr", []) or []:
        payload = common.json_de(x)
        filas = common.extraer_historico(payload, symbol) if payload is not None else []
        if len(filas) > len(mejor):
            mejor = filas
    if not mejor:
        common.guardar_debug(resp, symbol)
        raise RuntimeError(f"sin historial en las XHR (HTTP {resp.status}); ver debug/{symbol}/")
    return mejor


def por_api(symbol, dias, sesion):
    hasta = date.today()
    desde = hasta - timedelta(days=dias)
    api = config.API_HISTORICO.format(
        symbol=symbol, desde=desde.isoformat(), hasta=hasta.isoformat(),
        limite=max(dias, 100))
    salida = {}
    url = config.URL_HISTORICO.format(symbol=symbol)
    resp = common.fetch_pagina(url, sesion=sesion, page_action=common.accion_api(api, salida))
    if "error" in salida:
        raise RuntimeError(f"error en el navegador: {salida['error']}")
    res = salida.get("res")
    if not res:
        raise RuntimeError(f"no se ejecuto la llamada a la API (HTTP pagina {resp.status})")
    if res["status"] != 200:
        raise RuntimeError(f"API HTTP {res['status']}: {res['text'][:150]!r}")
    filas = common.extraer_historico(json.loads(res["text"]), symbol)
    if not filas:
        raise RuntimeError("la API respondio 200 pero sin filas reconocibles: "
                           f"{res['text'][:150]!r}")
    return filas


def procesar(con, simbolos, modo, dias, forzar, sesion, corte, pausa=None):
    """Descarga y guarda. Devuelve (ok, fallos, omitidos)."""
    pausa = config.PAUSA_ENTRE_SIMBOLOS if pausa is None else pausa
    ok, fallos, omitidos = 0, [], []
    for i, sym in enumerate(simbolos):
        ult = db.ultima_fecha(con, sym)
        if ult and not forzar and (corte - date.fromisoformat(ult)).days > config.DIAS_PARA_VENCIDO:
            print(f"{sym}: vencido (ultimo dato {ult}), omitido")
            omitidos.append(sym)
            continue
        try:
            filas = por_pagina(sym, sesion) if modo == "pagina" else por_api(sym, dias, sesion)
            total = len(filas)
            filas = [f for f in filas if f["fecha"] <= corte.isoformat()]
            if not filas:
                raise RuntimeError("todas las filas eran posteriores al corte")
            n = db.guardar_historico(con, filas)
            parcial = f", {total - len(filas)} parcial(es) descartada(s)" if total > len(filas) else ""
            print(f"{sym}: {n} filas ({filas[0]['fecha']} -> {filas[-1]['fecha']}){parcial}")
            ok += 1
        except Exception as e:
            print(f"{sym}: ERROR {e}", file=sys.stderr)
            fallos.append(sym)
        if i < len(simbolos) - 1 and pausa:
            time.sleep(pausa)
    return ok, fallos, omitidos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--simbolos", nargs="+", default=None)
    ap.add_argument("--modo", choices=["pagina", "api"], default="api")
    ap.add_argument("--dias", type=int, default=730)
    ap.add_argument("--forzar", action="store_true", help="reintentar tambien contratos vencidos")
    a = ap.parse_args()

    corte = common.fecha_corte()
    simbolos = (a.simbolos or config.SIMBOLOS_HISTORICO
                or common.lista_simbolos(config.RAICES, config.MESES_ADELANTE))
    print(f"Corte (ultima sesion final): {corte} | {len(simbolos)} contratos: {' '.join(simbolos)}\n")

    con = db.conectar()
    borradas = db.eliminar_posteriores(con, corte.isoformat())
    if borradas:
        print(f"Limpieza: {borradas} fila(s) parciales de corridas anteriores eliminadas\n")

    with common.abrir_sesion() as sesion:
        ok, fallos, omitidos = procesar(con, simbolos, a.modo, a.dias, a.forzar, sesion, corte)

    print(f"\nListo: {ok} ok, {len(fallos)} con error {fallos or ''}, {len(omitidos)} vencidos omitidos")
    print(f"Base de datos: {config.DB_PATH}")
    return 0 if ok or omitidos else 1


if __name__ == "__main__":
    sys.exit(main())
