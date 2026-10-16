
"""
PASO 2 - Descarga el historial diario de cada contrato y lo guarda en SQLite.

Por defecto:
  - Lee todos los contratos del catálogo generado por diagnostico_contratos.py.
  - Consulta el histórico mediante la API de Barchart.
  - Reutiliza una única sesión de navegador.
  - Descarta filas posteriores a la última sesión final.
  - Omite contratos vencidos que ya tienen datos antiguos.

Modos:
  --modo pagina  utiliza el historial capturado al cargar la página.
  --modo api     consulta el endpoint histórico desde el navegador.

Uso:
    python paso2_historico.py
    python paso2_historico.py --simbolos CLX26 HOX26 --dias 730
    python paso2_historico.py --forzar
    python paso2_historico.py --catalogo debug/catalogo_contratos/catalogo_general.json
"""

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import common
import config
import db


def cargar_simbolos_catalogo(ruta):
    """
    Lee y valida el catálogo general.

    Verifica:
      - Que el archivo exista y contenga la estructura esperada.
      - Que no existan símbolos duplicados.
      - Que el total declarado coincida con los símbolos únicos.
      - Que estén presentes las raíces configuradas.
      - Que las cantidades por raíz coincidan con el catálogo.

    Devuelve la lista de símbolos para consultar.
    """

    archivo = Path(ruta)

    if not archivo.is_file():
        raise FileNotFoundError(
            f"No existe el catálogo de contratos: {archivo}\n"
            "Ejecutá primero: python diagnostico_contratos.py"
        )

    try:
        with archivo.open("r", encoding="utf-8") as f:
            catalogo = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"El catálogo no contiene JSON válido: {archivo}. Detalle: {e}"
        ) from e

    contratos = catalogo.get("contratos")
    resumen = catalogo.get("resumen_por_raiz")
    total_declarado = catalogo.get("total_contratos_unicos")

    if not isinstance(contratos, list):
        raise ValueError(
            "El catálogo no contiene una lista válida en 'contratos'."
        )

    if not isinstance(resumen, dict):
        raise ValueError(
            "El catálogo no contiene un objeto válido en 'resumen_por_raiz'."
        )

    if not isinstance(total_declarado, int) or total_declarado < 1:
        raise ValueError(
            "El catálogo no contiene un total válido en "
            "'total_contratos_unicos'."
        )

    simbolos = []
    simbolos_vistos = set()
    cantidades_por_raiz = {}

    for contrato in contratos:
        if not isinstance(contrato, dict):
            raise ValueError(
                "El catálogo contiene un registro de contrato inválido."
            )

        simbolo = contrato.get("symbol")
        raiz = contrato.get("raiz_consultada")

        if not isinstance(simbolo, str) or not simbolo.strip():
            raise ValueError(
                "Se encontró un contrato sin un campo 'symbol' válido."
            )

        if not isinstance(raiz, str) or not raiz.strip():
            raise ValueError(
                f"El contrato {simbolo} no tiene 'raiz_consultada'."
            )

        simbolo = simbolo.strip()
        raiz = raiz.strip().upper()

        if simbolo in simbolos_vistos:
            raise ValueError(
                f"El catálogo contiene el símbolo duplicado: {simbolo}"
            )

        simbolos_vistos.add(simbolo)
        simbolos.append(simbolo)

        cantidades_por_raiz[raiz] = (
            cantidades_por_raiz.get(raiz, 0) + 1
        )

    if len(simbolos) != total_declarado:
        raise ValueError(
            "El catálogo parece incompleto o inconsistente: "
            f"declara {total_declarado} contratos, "
            f"pero contiene {len(simbolos)} símbolos únicos."
        )

    if sum(resumen.values()) != total_declarado:
        raise ValueError(
            "La suma de 'resumen_por_raiz' no coincide con "
            "'total_contratos_unicos'."
        )

    raices_configuradas = {
        raiz.upper() for raiz in config.RAICES
    }

    raices_catalogo = set(cantidades_por_raiz)

    faltantes = raices_configuradas - raices_catalogo

    if faltantes:
        raise ValueError(
            "Faltan raíces configuradas en el catálogo: "
            + ", ".join(sorted(faltantes))
        )

    for raiz, cantidad_declarada in resumen.items():
        cantidad_real = cantidades_por_raiz.get(raiz, 0)

        if cantidad_real != cantidad_declarada:
            raise ValueError(
                f"Cantidad inconsistente para {raiz}: "
                f"el resumen declara {cantidad_declarada}, "
                f"pero hay {cantidad_real} contratos."
            )

    print(f"Catálogo validado: {archivo}")
    print(f"Contratos únicos disponibles: {len(simbolos)}")

    for raiz in config.RAICES:
        raiz = raiz.upper()
        print(
            f"  {raiz}: "
            f"{cantidades_por_raiz.get(raiz, 0)} contratos"
        )

    return simbolos


def por_pagina(symbol, sesion):
    url = config.URL_HISTORICO.format(symbol=symbol)
    resp = common.fetch_pagina(url, sesion=sesion)

    mejor = []

    for x in getattr(resp, "captured_xhr", []) or []:
        payload = common.json_de(x)
        filas = (
            common.extraer_historico(payload, symbol)
            if payload is not None
            else []
        )

        if len(filas) > len(mejor):
            mejor = filas

    if not mejor:
        common.guardar_debug(resp, symbol)
        raise RuntimeError(
            f"sin historial en las XHR (HTTP {resp.status}); "
            f"ver debug/{symbol}/"
        )

    return mejor


def por_api(symbol, dias, sesion):
    hasta = date.today()
    desde = hasta - timedelta(days=dias)

    api = config.API_HISTORICO.format(
        symbol=symbol,
        desde=desde.isoformat(),
        hasta=hasta.isoformat(),
        limite=max(dias, 100),
    )

    salida = {}
    url = config.URL_HISTORICO.format(symbol=symbol)

    resp = common.fetch_pagina(
        url,
        sesion=sesion,
        page_action=common.accion_api(api, salida),
    )

    if "error" in salida:
        raise RuntimeError(
            f"error en el navegador: {salida['error']}"
        )

    res = salida.get("res")

    if not res:
        raise RuntimeError(
            f"no se ejecutó la llamada a la API "
            f"(HTTP página {resp.status})"
        )

    if res["status"] != 200:
        raise RuntimeError(
            f"API HTTP {res['status']}: {res['text'][:150]!r}"
        )

    try:
        payload = json.loads(res["text"])
    except (json.JSONDecodeError, TypeError) as e:
        raise RuntimeError(
            f"la API no devolvió JSON válido: {e}"
        ) from e

    filas = common.extraer_historico(payload, symbol)

    if not filas:
        raise RuntimeError(
            "la API respondió 200 pero sin filas reconocibles: "
            f"{res['text'][:150]!r}"
        )

    return filas


def procesar(
    con,
    simbolos,
    modo,
    dias,
    forzar,
    sesion,
    corte,
    pausa=None,
):
    """Descarga y guarda. Devuelve (ok, fallos, omitidos)."""

    pausa = (
        config.PAUSA_ENTRE_SIMBOLOS
        if pausa is None
        else pausa
    )

    ok = 0
    fallos = []
    omitidos = []

    for i, sym in enumerate(simbolos):
        ult = db.ultima_fecha(con, sym)

        if (
            ult
            and not forzar
            and (
                corte - date.fromisoformat(ult)
            ).days > config.DIAS_PARA_VENCIDO
        ):
            print(
                f"{sym}: vencido "
                f"(último dato {ult}), omitido"
            )
            omitidos.append(sym)
            continue

        try:
            if modo == "pagina":
                filas = por_pagina(sym, sesion)
            else:
                filas = por_api(sym, dias, sesion)

            total = len(filas)

            filas = [
                f
                for f in filas
                if f["fecha"] <= corte.isoformat()
            ]

            if not filas:
                raise RuntimeError(
                    "todas las filas eran posteriores al corte"
                )

            n = db.guardar_historico(con, filas)

            parcial = (
                f", {total - len(filas)} parcial(es) descartada(s)"
                if total > len(filas)
                else ""
            )

            print(
                f"{sym}: {n} filas "
                f"({filas[0]['fecha']} -> {filas[-1]['fecha']})"
                f"{parcial}"
            )

            ok += 1

        except Exception as e:
            print(
                f"{sym}: ERROR {e}",
                file=sys.stderr,
            )
            fallos.append(sym)

        if i < len(simbolos) - 1 and pausa:
            time.sleep(pausa)

    return ok, fallos, omitidos


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Descarga históricos de contratos de Barchart "
            "y los guarda en SQLite."
        )
    )

    ap.add_argument(
        "--simbolos",
        nargs="+",
        default=None,
        help="Procesar únicamente los símbolos indicados.",
    )

    ap.add_argument(
        "--modo",
        choices=["pagina", "api"],
        default="api",
        help="Método de consulta del histórico.",
    )

    ap.add_argument(
        "--dias",
        type=int,
        default=730,
        help="Cantidad de días históricos solicitados.",
    )

    ap.add_argument(
        "--forzar",
        action="store_true",
        help="Reintentar también contratos vencidos.",
    )

    ap.add_argument(
        "--catalogo",
        default=str(
            Path(config.DEBUG_DIR)
            / "catalogo_contratos"
            / "catalogo_general.json"
        ),
        help="Ruta al catálogo general de contratos.",
    )

    a = ap.parse_args()

    if a.dias < 1:
        ap.error("--dias debe ser mayor que cero.")

    corte = common.fecha_corte()

    # Si se indican símbolos explícitos, se respeta esa selección.
    # En caso contrario, se utiliza el catálogo completo validado.
    if a.simbolos:
        simbolos = list(dict.fromkeys(a.simbolos))
        origen = "argumento --simbolos"
    else:
        try:
            simbolos = cargar_simbolos_catalogo(a.catalogo)
        except (OSError, ValueError) as e:
            print(
                f"ERROR al cargar el catálogo: {e}",
                file=sys.stderr,
            )
            return 1

        origen = a.catalogo

    if not simbolos:
        print(
            "ERROR: no hay contratos para procesar.",
            file=sys.stderr,
        )
        return 1

    print(f"\nOrigen de contratos: {origen}")
    print(f"Modo: {a.modo} | Días solicitados: {a.dias}")
    print(
        f"Corte (última sesión final): {corte} "
        f"| {len(simbolos)} contratos seleccionados"
    )
    print()

    con = db.conectar()

    try:
        # Se conserva la limpieza preexistente de filas posteriores
        # a la fecha de corte. No se borran históricos anteriores.
        borradas = db.eliminar_posteriores(
            con,
            corte.isoformat(),
        )

        if borradas:
            print(
                f"Limpieza: {borradas} fila(s) posteriores "
                "al corte eliminadas\n"
            )

        with common.abrir_sesion() as sesion:
            ok, fallos, omitidos = procesar(
                con=con,
                simbolos=simbolos,
                modo=a.modo,
                dias=a.dias,
                forzar=a.forzar,
                sesion=sesion,
                corte=corte,
            )

    finally:
        con.close()

    print("\n" + "=" * 60)
    print("RESUMEN DE DESCARGA")
    print("=" * 60)
    print(f"Contratos seleccionados: {len(simbolos)}")
    print(f"Procesados correctamente: {ok}")
    print(f"Contratos con error: {len(fallos)}")
    print(f"Contratos omitidos por vencimiento: {len(omitidos)}")

    if fallos:
        print("\nContratos con error:")
        for sym in fallos:
            print(f"  - {sym}")

    if omitidos:
        print("\nContratos omitidos:")
        for sym in omitidos:
            print(f"  - {sym}")

    print(f"\nBase de datos: {config.DB_PATH}")

    return 0 if ok or omitidos else 1


if __name__ == "__main__":
    sys.exit(main())
