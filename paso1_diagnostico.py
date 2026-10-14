"""
PASO 1 - Diagnostico: ¿Scrapling pasa el anti-bot de Barchart y que peticiones hace la pagina?

Uso:
    python paso1_diagnostico.py                 # usa CLX26
    python paso1_diagnostico.py HOX26
    python paso1_diagnostico.py CLX26 --patron "."   # captura TODAS las XHR (mas ruido)

Que hace: abre la pagina de historial del contrato, espera, y lista cada peticion
de fondo (XHR/fetch) que coincide con el patron. Guarda todo en debug/<simbolo>/.
"""
import argparse
import sys

import common
import config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", nargs="?", default="CLX26")
    ap.add_argument("--patron", default=config.XHR_PATRON,
                    help="regex sobre la URL de las XHR a capturar")
    a = ap.parse_args()

    url = config.URL_HISTORICO.format(symbol=a.symbol)
    print(f"Abriendo {url}\n(patron XHR: {a.patron!r}, headless={config.HEADLESS})\n")

    resp = common.fetch_pagina(url, patron=a.patron)
    html = common.cuerpo_texto(resp)
    titulo = resp.css("title::text").get() if html else None
    print(f"HTTP {resp.status} | HTML: {len(html):,} caracteres | titulo: {titulo!r}")

    capturadas = getattr(resp, "captured_xhr", []) or []
    print(f"\nXHR capturadas: {len(capturadas)}")
    mejor = None
    for i, x in enumerate(capturadas):
        payload = common.json_de(x)
        filas = common.extraer_historico(payload, a.symbol) if payload is not None else []
        marca = f"  <-- {len(filas)} filas de historial" if filas else ""
        print(f"  [{i:02d}] HTTP {x.status}  {x.url[:110]}{marca}")
        if filas and (mejor is None or len(filas) > len(mejor[1])):
            mejor = (x.url, filas)

    carpeta = common.guardar_debug(resp, a.symbol)
    print(f"\nDetalle guardado en: {carpeta}")

    print("\n" + "=" * 60)
    if mejor:
        url_h, filas = mejor
        print("RESULTADO: OK, se detecto el historial.")
        print(f"Endpoint: {url_h}")
        print(f"Filas: {len(filas)} | de {filas[0]['fecha']} a {filas[-1]['fecha']}")
        print("Ultimas 3 filas:")
        for f in filas[-3:]:
            print("  ", f)
        print("\nSiguiente: python paso2_historico.py --modo pagina")
        return 0
    if resp.status in (202, 403, 429, 503) or len(html) < 2000:
        print("RESULTADO: BLOQUEADO (anti-bot). Scrapling no paso el desafio.")
        print("Prueba HEADLESS = False en config.py, o usa el scraper con Playwright.")
    elif not capturadas:
        print("RESULTADO: la pagina cargo pero no se capturo ninguna XHR.")
        print("Prueba:  python paso1_diagnostico.py", a.symbol, '--patron "."')
        print("y revisa debug/ para ver que pide la pagina.")
    else:
        print("RESULTADO: hubo XHR pero ninguna con historial reconocible.")
        print(f"Revisa debug/{a.symbol}/indice.txt y mandame esas URLs.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
