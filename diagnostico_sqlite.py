
"""
Diagnóstico de SQLite para el proyecto barchart_scraping.

- Lee barchart.db.
- Lista tablas, columnas e índices.
- Muestra la cantidad de registros.
- Identifica posibles duplicados en columnas candidatas.
- No modifica ni elimina datos.
"""

import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "barchart.db"


def diagnosticar():
    if not DB_PATH.exists():
        print(f"ERROR: No existe la base de datos: {DB_PATH}")
        return 1

    con = sqlite3.connect(str(DB_PATH))

    try:
        cur = con.cursor()

        print("=" * 75)
        print("DIAGNÓSTICO DE SQLITE")
        print("=" * 75)
        print(f"Archivo: {DB_PATH}")
        print(f"Tamaño: {DB_PATH.stat().st_size:,} bytes")

        tablas = cur.execute("""
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """).fetchall()

        if not tablas:
            print("\nNo se encontraron tablas.")
            return 0

        for nombre, ddl in tablas:
            print("\n" + "=" * 75)
            print(f"TABLA: {nombre}")
            print("=" * 75)

            columnas = cur.execute(
                f'PRAGMA table_info("{nombre}")'
            ).fetchall()

            print("\nColumnas:")
            nombres_columnas = []

            for col in columnas:
                # cid, name, type, notnull, dflt_value, pk
                cid, nom, tipo, notnull, default, pk = col
                nombres_columnas.append(nom)

                print(
                    f"  {nom} | tipo={tipo or 'sin tipo'}"
                    f" | NOT NULL={bool(notnull)}"
                    f" | PK={pk}"
                    f" | default={default}"
                )

            cantidad = cur.execute(
                f'SELECT COUNT(*) FROM "{nombre}"'
            ).fetchone()[0]

            print(f"\nTotal de registros: {cantidad:,}")

            indices = cur.execute(
                f'PRAGMA index_list("{nombre}")'
            ).fetchall()

            print("\nÍndices:")

            if not indices:
                print("  No hay índices declarados.")
            else:
                for indice in indices:
                    # seq, name, unique, origin, partial
                    _, nombre_indice, unico, origen, parcial = indice

                    detalle = cur.execute(
                        f'PRAGMA index_info("{nombre_indice}")'
                    ).fetchall()

                    columnas_indice = [
                        fila[2] for fila in detalle
                    ]

                    print(
                        f"  {nombre_indice}: "
                        f"columnas={columnas_indice}, "
                        f"único={bool(unico)}, "
                        f"origen={origen}, "
                        f"parcial={bool(parcial)}"
                    )

            # Revisar duplicados cuando existen columnas típicas
            # para identificar un registro histórico.
            candidatos = [
                ("symbol", "fecha"),
                ("simbolo", "fecha"),
                ("symbol", "trade_date"),
                ("symbol", "date"),
                ("simbolo", "fecha_operacion"),
            ]

            combinacion = next(
                (
                    pareja for pareja in candidatos
                    if all(c in nombres_columnas for c in pareja)
                ),
                None,
            )

            if combinacion and cantidad:
                col_simbolo, col_fecha = combinacion

                print(
                    f"\nControl de duplicados por "
                    f"{col_simbolo} + {col_fecha}:"
                )

                consulta = f"""
                    SELECT
                        "{col_simbolo}",
                        "{col_fecha}",
                        COUNT(*) AS repeticiones
                    FROM "{nombre}"
                    GROUP BY "{col_simbolo}", "{col_fecha}"
                    HAVING COUNT(*) > 1
                    ORDER BY repeticiones DESC
                    LIMIT 10
                """

                duplicados = cur.execute(consulta).fetchall()

                if duplicados:
                    print("  Se encontraron posibles duplicados:")
                    for fila in duplicados:
                        print(f"  {fila}")
                else:
                    print("  No se encontraron duplicados.")

            elif cantidad:
                print(
                    "\nControl de duplicados: no se identificó "
                    "automáticamente una combinación de columnas "
                    "de símbolo y fecha."
                )

            if ddl:
                print("\nDefinición SQL:")
                print(ddl)

        print("\n" + "=" * 75)
        print("FIN DEL DIAGNÓSTICO")
        print("La base de datos no fue modificada.")
        print("=" * 75)

        return 0

    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(diagnosticar())
