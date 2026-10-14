"""Lee la conexion a Postgres desde variables de entorno o un archivo .env (sin dependencias)."""
import os
from pathlib import Path


def cargar_env(ruta=".env"):
    p = Path(ruta)
    if not p.exists():
        return
    for linea in p.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def parametros():
    cargar_env()
    return {
        "host": os.environ.get("PGHOST", "localhost"),
        "port": int(os.environ.get("PGPORT", "5432")),
        "dbname": os.environ.get("PGDATABASE", "newpreciofuturo"),
        "user": os.environ.get("PGUSER", ""),
        "password": os.environ.get("PGPASSWORD", ""),
    }


def tabla():
    cargar_env()
    return os.environ.get("PG_TABLE", "")
