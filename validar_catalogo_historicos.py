
import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "barchart.db"
CATALOGO_PATH = (
    BASE_DIR
    / "debug"
    / "catalogo_contratos"
    / "catalogo_general.json"
)


def main():
    if not DB_PATH.is_file():
        raise FileNotFoundError(f"No existe la base: {DB_PATH}")

    if not CATALOGO_PATH.is_file():
        raise FileNotFoundError(
            f"No existe el catálogo: {CATALOGO_PATH}\n"
            "Ejecutá primero: python diagnostico_contratos.py"
        )

    with CATALOGO_PATH.open("r", encoding="utf-8") as f:
        catalogo = json.load(f)

    contratos = catalogo.get("contratos", [])
    esperados = {
        c["symbol"]: c.get("raiz_consultada", "")
        for c in contratos
        if isinstance(c, dict)
        and isinstance(c.get("symbol"), str)
        and c["symbol"].strip()
    }

    if not esperados:
        raise ValueError("El catálogo no contiene contratos válidos.")

    if len(esperados) != catalogo.get("total_contratos_unicos"):
        raise ValueError(
            "El catálogo contiene símbolos duplicados o el total declarado "
            "no coincide con la cantidad de contratos."
        )

    con = sqlite3.connect(str(DB_PATH))

    try:
        cur = con.cursor()

        existentes = cur.execute("""
            SELECT
                symbol,
                COUNT(*) AS registros,
                MIN(fecha) AS fecha_inicial,
                MAX(fecha) AS fecha_final
            FROM historico_diario
            GROUP BY symbol
            ORDER BY symbol
        """).fetchall()

        por_simbolo = {
            symbol: {
                "registros": cantidad,
                "desde": desde,
                "hasta": hasta,
            }
            for symbol, cantidad, desde, hasta in existentes
        }

        total_catalogo = len(esperados)
        con_historico = [
            s for s in esperados if s in por_simbolo
        ]
        sin_historico = [
            s for s in esperados if s not in por_simbolo
        ]
        fuera_catalogo = sorted(
            set(por_simbolo) - set(esperados)
        )

        print("=" * 78)
        print("VALIDACIÓN DEL CATÁLOGO CONTRA SQLITE")
        print("=" * 78)
        print(f"Base: {DB_PATH}")
        print(f"Catálogo: {CATALOGO_PATH}")
        print(f"Contratos en catálogo: {total_catalogo}")
        print(f"Contratos con histórico: {len(con_historico)}")
        print(f"Contratos sin histórico: {len(sin_historico)}")
        print(f"Símbolos en SQLite fuera del catálogo: {len(fuera_catalogo)}")

        print("\nRESUMEN POR RAÍZ")

        for raiz in sorted(set(esperados.values())):
            simbolos_raiz = [
                s for s, r in esperados.items() if r == raiz
            ]
            con_datos = [
                s for s in simbolos_raiz if s in por_simbolo
            ]
            print(
                f"{raiz}: {len(con_datos)}/{len(simbolos_raiz)} "
                "contratos con histórico"
            )

        print("\nDETALLE DE CONTRATOS DEL CATÁLOGO")

        for symbol in sorted(esperados):
            raiz = esperados[symbol]
            datos = por_simbolo.get(symbol)

            if datos:
                print(
                    f"{symbol} [{raiz}]: "
                    f"{datos['registros']:,} registros | "
                    f"{datos['desde']} -> {datos['hasta']}"
                )
            else:
                print(f"{symbol} [{raiz}]: SIN HISTÓRICO")

        if fuera_catalogo:
            print("\nSÍMBOLOS EXISTENTES FUERA DEL CATÁLOGO")
            for symbol in fuera_catalogo:
                datos = por_simbolo[symbol]
                print(
                    f"{symbol}: {datos['registros']:,} registros | "
                    f"{datos['desde']} -> {datos['hasta']}"
                )

        print("\nNo se modificaron datos.")

    finally:
        con.close()


if __name__ == "__main__":
    main()
