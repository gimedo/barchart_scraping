"""
Diagnóstico y descubrimiento de contratos publicados por Barchart.

Consulta el endpoint quotes/get capturado desde la página de Barchart.
Detecta paginación y guarda un catálogo JSON por raíz y uno consolidado.

No modifica SQLite ni PostgreSQL.

Uso:
    python diagnostico_contratos.py
    python diagnostico_contratos.py CL
    python diagnostico_contratos.py CL RB
"""

import json
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import common
import config


DIRECTORIO_SALIDA = Path("debug") / "catalogo_contratos"


def es_endpoint_contratos(url, raiz):
    """Identifica el endpoint de listado de contratos para una raíz."""
    if not url:
        return False

    partes = urlsplit(url)
    parametros = parse_qs(partes.query)

    return (
        "/proxies/core-api/v1/quotes/get" in partes.path
        and parametros.get("root", [""])[0].upper() == raiz.upper()
        and parametros.get("lists", [""])[0] == "futures.contractInRoot"
    )


def buscar_endpoint(resp, raiz):
    """Busca la petición de contratos entre las XHR capturadas."""
    capturadas = getattr(resp, "captured_xhr", []) or []

    for xhr in capturadas:
        if not es_endpoint_contratos(
            getattr(xhr, "url", ""),
            raiz,
        ):
            continue

        payload = common.json_de(xhr)

        if (
            isinstance(payload, dict)
            and isinstance(payload.get("data"), list)
        ):
            return xhr.url, payload

    return None, None


def construir_url_pagina(url_base, pagina):
    """Cambia el número de página sin alterar los demás parámetros."""
    partes = urlsplit(url_base)
    parametros = parse_qs(
        partes.query,
        keep_blank_values=True,
    )

    parametros["page"] = [str(pagina)]

    return urlunsplit(
        (
            partes.scheme,
            partes.netloc,
            partes.path,
            urlencode(parametros, doseq=True),
            partes.fragment,
        )
    )


def obtener_pagina_adicional(sesion, url, raiz, pagina):
    """
    Consulta otra página mediante fetch desde el navegador.

    Reutiliza la sesión abierta y las cookies del navegador.
    """
    salida = {}

    try:
        accion = common.accion_api(url, salida)

        url_pagina = (
            "https://www.barchart.com/futures/quotes/"
            f"{raiz}%2A0/futures-prices?viewName=main"
        )

        common.fetch_pagina(
            url_pagina,
            page_action=accion,
            sesion=sesion,
        )

        if "error" in salida:
            print(
                f"  Página {pagina}: error de ejecución: "
                f"{salida['error']}"
            )
            return None

        resultado = salida.get("res")

        if not isinstance(resultado, dict):
            print(
                f"  Página {pagina}: no se recibió una respuesta válida."
            )
            return None

        estado = resultado.get("status")
        texto = resultado.get("text", "")

        if estado != 200:
            print(f"  Página {pagina}: HTTP {estado}")
            return None

        if isinstance(texto, str):
            payload = json.loads(texto)
        elif isinstance(texto, dict):
            payload = texto
        else:
            print(
                f"  Página {pagina}: formato de respuesta inesperado."
            )
            return None

        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("data"), list)
        ):
            print(
                f"  Página {pagina}: JSON sin una lista de contratos."
            )
            return None

        return payload

    except Exception as exc:
        print(f"  Error al consultar página {pagina}: {exc}")
        return None


def guardar_json(ruta, contenido):
    """Guarda JSON legible en UTF-8."""
    ruta.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ruta.write_text(
        json.dumps(
            contenido,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def normalizar_contrato(fila, raiz):
    """Conserva los campos originales y agrega la raíz consultada."""
    contrato = dict(fila)
    contrato["raiz_consultada"] = raiz
    return contrato


def diagnosticar_raiz(raiz):
    """Descubre y guarda los contratos publicados de una raíz."""
    raiz = raiz.upper()

    url_pagina = (
        "https://www.barchart.com/futures/quotes/"
        f"{raiz}%2A0/futures-prices?viewName=main"
    )

    print("\n" + "=" * 72)
    print(f"RAÍZ: {raiz}")
    print(f"URL: {url_pagina}")
    print("=" * 72)

    # La sesión debe permanecer abierta durante toda la consulta,
    # incluida la recuperación de las páginas adicionales.
    with common.abrir_sesion(patron="core-api") as sesion:
        resp = common.fetch_pagina(
            url_pagina,
            patron="core-api",
            sesion=sesion,
        )

        html = common.cuerpo_texto(resp)

        print(f"HTTP página: {resp.status}")
        print(f"Tamaño HTML: {len(html):,} caracteres")

        carpeta_debug = common.guardar_debug(
            resp,
            f"contratos_{raiz}",
        )

        print(f"Diagnóstico guardado en: {carpeta_debug}")

        if resp.status != 200:
            print("No se pudo consultar la página.")
            return []

        url_api, primera_respuesta = buscar_endpoint(
            resp,
            raiz,
        )

        if primera_respuesta is None:
            print(
                "No se encontró una respuesta JSON válida de quotes/get "
                "para esta raíz."
            )
            print(
                f"Revisá debug/contratos_{raiz}/indice.txt "
                "para inspeccionar las solicitudes capturadas."
            )
            return []

        total_original = primera_respuesta.get("total")
        filas_iniciales = primera_respuesta.get("data", [])
        count = primera_respuesta.get(
            "count",
            len(filas_iniciales),
        )

        print(
            f"\nContratos en primera respuesta: "
            f"{len(filas_iniciales)}"
        )
        print(f"Count informado: {count}")
        print(f"Total informado: {total_original}")

        try:
            total = int(total_original)
        except (TypeError, ValueError):
            total = None

        contratos = {}

        for fila in filas_iniciales:
            if not isinstance(fila, dict):
                continue

            simbolo = fila.get("symbol")

            if simbolo:
                clave = str(simbolo).upper()
                contratos[clave] = normalizar_contrato(
                    fila,
                    raiz,
                )

        # Determinar el límite utilizado por el endpoint.
        try:
            parametros = parse_qs(urlsplit(url_api).query)
            limite = int(
                parametros.get("limit", ["100"])[0]
            )
        except (TypeError, ValueError):
            limite = 100

        if limite < 1:
            limite = 100

        if total is None:
            print(
                "No se pudo interpretar el total informado. "
                "No se puede garantizar que el catálogo esté completo."
            )
            paginas_necesarias = 1
        else:
            paginas_necesarias = max(
                1,
                (total + limite - 1) // limite,
            )

        print(f"Páginas estimadas: {paginas_necesarias}")

        errores_paginas = []

        for pagina in range(2, paginas_necesarias + 1):
            url_pagina_api = construir_url_pagina(
                url_api,
                pagina,
            )

            print(f"\nConsultando página {pagina}...")

            payload = obtener_pagina_adicional(
                sesion,
                url_pagina_api,
                raiz,
                pagina,
            )

            if payload is None:
                errores_paginas.append(pagina)
                print(
                    f"No se pudo recuperar la página {pagina}."
                )
                continue

            filas = payload.get("data", [])

            print(f"Contratos recibidos: {len(filas)}")

            for fila in filas:
                if not isinstance(fila, dict):
                    continue

                simbolo = fila.get("symbol")

                if simbolo:
                    clave = str(simbolo).upper()
                    contratos[clave] = normalizar_contrato(
                        fila,
                        raiz,
                    )

            time.sleep(1)

        lista = sorted(
            contratos.values(),
            key=lambda item: str(item.get("symbol", "")),
        )

        # Solo se marca como completo si se recibieron todos los
        # registros esperados y no hubo errores de paginación.
        catalogo_completo = (
            total is not None
            and len(lista) >= total
            and not errores_paginas
        )

        resultado = {
            "raiz": raiz,
            "url_api": url_api,
            "total_informado": total_original,
            "contratos_unicos": len(lista),
            "catalogo_completo": catalogo_completo,
            "paginas_con_error": errores_paginas,
            "contratos": lista,
        }

        guardar_json(
            DIRECTORIO_SALIDA / f"contratos_{raiz}.json",
            resultado,
        )

        print("\nRESUMEN")
        print(f"Raíz: {raiz}")
        print(f"Contratos únicos: {len(lista)}")
        print(f"Total informado: {total_original}")
        print(
            "Catálogo completo: "
            + ("SÍ" if catalogo_completo else "NO")
        )

        if errores_paginas:
            print(f"Páginas con error: {errores_paginas}")

        print("\nMuestra de contratos:")

        for contrato in lista[:8]:
            print(
                f"  {contrato.get('symbol')} | "
                f"{contrato.get('contractSymbol')} | "
                f"Último: {contrato.get('lastPrice')}"
            )

        return lista


def main():
    """Procesa las raíces solicitadas o las definidas en config.py."""
    raices = (
        [raiz.upper() for raiz in sys.argv[1:]]
        if len(sys.argv) > 1
        else config.RAICES
    )

    catalogo_general = []
    resumen = {}

    for indice, raiz in enumerate(raices):
        try:
            contratos = diagnosticar_raiz(raiz)
            resumen[raiz] = len(contratos)
            catalogo_general.extend(contratos)

        except Exception as exc:
            print(
                f"\nERROR procesando {raiz}: {exc}",
                file=sys.stderr,
            )
            resumen[raiz] = 0

        if indice < len(raices) - 1:
            time.sleep(config.PAUSA_ENTRE_SIMBOLOS)

    unicos = {}

    for contrato in catalogo_general:
        clave = (
            contrato.get("raiz_consultada"),
            str(contrato.get("symbol", "")).upper(),
        )
        unicos[clave] = contrato

    catalogo = sorted(
        unicos.values(),
        key=lambda item: (
            item.get("raiz_consultada", ""),
            item.get("symbol", ""),
        ),
    )

    guardar_json(
        DIRECTORIO_SALIDA / "catalogo_general.json",
        {
            "total_contratos_unicos": len(catalogo),
            "resumen_por_raiz": resumen,
            "contratos": catalogo,
        },
    )

    print("\n" + "=" * 72)
    print("RESUMEN GENERAL")
    print("=" * 72)

    for raiz, cantidad in resumen.items():
        print(f"{raiz}: {cantidad} contratos")

    print(f"Total consolidado: {len(catalogo)}")
    print(f"Archivos guardados en: {DIRECTORIO_SALIDA}")
    print("No se modificaron SQLite ni PostgreSQL.")

    return 0


if __name__ == "__main__":
    sys.exit(main())