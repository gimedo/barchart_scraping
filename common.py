"""Utilidades compartidas: descarga con Scrapling y normalizacion de filas."""
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

import config

# ---------------------------------------------------------------- descarga
def abrir_sesion(patron=None):
    """Sesion con el navegador abierto: se reutiliza entre simbolos (mucho mas rapido).
    Uso:  with abrir_sesion() as s:  fetch_pagina(url, sesion=s)"""
    from scrapling.fetchers import StealthySession

    kwargs = dict(
        headless=config.HEADLESS,
        network_idle=True,
        capture_xhr=patron or config.XHR_PATRON,
    )
    if config.CDP_URL:  # Chrome ya abierto (servicio): Scrapling se conecta en vez de lanzar uno
        kwargs["cdp_url"] = config.CDP_URL
    return StealthySession(**kwargs)


def fetch_pagina(url, patron=None, page_action=None, sesion=None):
    """Abre la pagina con Scrapling y captura XHR. Con 'sesion' reutiliza el navegador."""
    if sesion is not None:
        kwargs = dict(wait=config.ESPERA_MS)
        if page_action is not None:
            kwargs["page_action"] = page_action
        return sesion.fetch(url, **kwargs)

    from scrapling.fetchers import StealthyFetcher

    kwargs = dict(
        headless=config.HEADLESS,
        network_idle=True,
        wait=config.ESPERA_MS,
        capture_xhr=patron or config.XHR_PATRON,
    )
    if page_action is not None:
        kwargs["page_action"] = page_action
    return StealthyFetcher.fetch(url, **kwargs)


# ------------------------------------------------- sesion de la bolsa (Chicago)
def ahora_chicago():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Chicago"))
    except Exception:  # sin tzdata (Windows): aproximacion UTC-5
        return datetime.utcnow() - timedelta(hours=5)


def fecha_corte(ahora=None):
    """Ultima fecha de negociacion con datos FINALES.
    Las filas posteriores son parciales (sesion abierta o recien abierta, p. ej. la
    sesion nocturna que ya lleva la fecha del dia siguiente) y se descartan.
    El petroleo liquida ~13:30 hora de Chicago: antes de las 14:00 el dia de hoy aun no es final."""
    ahora = ahora or ahora_chicago()
    hoy = ahora.date()
    return hoy if ahora.hour >= 14 else hoy - timedelta(days=1)


def lista_simbolos(raices, n, hoy=None):
    """Genera los simbolos de los proximos n meses para cada raiz (CLX26, CLZ26...)."""
    hoy = hoy or ahora_chicago().date()
    letras = "FGHJKMNQUVXZ"
    salida = []
    for i in range(n):
        idx = hoy.month - 1 + i
        anio = hoy.year + idx // 12
        for r in raices:
            salida.append(f"{r}{letras[idx % 12]}{str(anio)[2:]}")
    return salida


JS_FETCH = """
async (url) => {
  const r = await fetch(url, {credentials: 'same-origin',
                              headers: {'accept': 'application/json'}});
  return {status: r.status, text: await r.text()};
}
"""


def accion_api(url, salida):
    """page_action que llama a un endpoint desde dentro del navegador."""
    def _accion(page):
        try:
            salida["res"] = page.evaluate(JS_FETCH, url)
        except Exception as e:  # Scrapling solo registra errores de page_action
            salida["error"] = str(e)
    return _accion


def cuerpo_texto(resp):
    body = resp.body
    if isinstance(body, bytes):
        return body.decode("utf-8", "ignore")
    return str(body or "")


def json_de(resp):
    try:
        return resp.json()
    except Exception:
        try:
            return json.loads(cuerpo_texto(resp))
        except Exception:
            return None


def guardar_debug(resp, nombre):
    """Guarda HTML y cada XHR capturado en debug/<nombre>/ para inspeccionarlos."""
    carpeta = Path(config.DEBUG_DIR) / nombre
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "pagina.html").write_text(cuerpo_texto(resp), encoding="utf-8")
    indice = []
    for i, x in enumerate(getattr(resp, "captured_xhr", []) or []):
        slug = re.sub(r"[^A-Za-z0-9]+", "_", x.url.split("?")[0])[-60:]
        ruta = carpeta / f"{i:02d}_{slug}.json"
        ruta.write_text(cuerpo_texto(x), encoding="utf-8")
        indice.append(f"{i:02d} HTTP {x.status} {x.url}")
    (carpeta / "indice.txt").write_text("\n".join(indice), encoding="utf-8")
    return carpeta


# ------------------------------------------------------------ normalizacion
CLAVES = {
    "fecha": ("tradeTime", "tradeDate", "date", "time"),
    "open": ("openPrice", "open"),
    "high": ("highPrice", "high"),
    "low": ("lowPrice", "low"),
    "close": ("lastPrice", "closePrice", "close", "last", "settlement"),
    "change": ("priceChange", "change"),
    "pct_change": ("percentChange", "pctChange"),
    "volume": ("volume",),
    "open_interest": ("openInterest", "oi"),
}


def a_numero(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().lower()
    if s in ("", "n/a", "na", "-", "null"):
        return None
    if s == "unch":
        return 0.0
    s = s.replace(",", "").replace("%", "").replace("+", "")
    try:
        return float(s)
    except ValueError:
        return None


def a_fecha(v):
    if v is None or v == "":
        return None
    try:
        if isinstance(v, (int, float)) and v > 1e9:
            seg = v / 1000 if v > 1e11 else v
            return datetime.fromtimestamp(seg).date().isoformat()
        ts = pd.to_datetime(str(v), errors="coerce")
        if pd.isna(ts):
            return None
        return ts.date().isoformat()
    except Exception:
        return None


def _pct_a_porcentaje(pct, change, close):
    """La API con raw=1 entrega percentChange como fraccion (0.0206 = 2.06%).
    Se compara con el cambio implicito y se escala a porcentaje si hace falta."""
    if pct is None or change is None or close is None or close == change:
        return pct
    implicito = change / (close - change) * 100
    return pct * 100 if abs(pct * 100 - implicito) < abs(pct - implicito) else pct


def normalizar_fila(item, symbol):
    if not isinstance(item, dict):
        return None
    raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}

    def tomar(nombres):
        for n in nombres:
            if n in raw and raw[n] not in (None, ""):
                return raw[n]
            if n in item and item[n] not in (None, ""):
                return item[n]
        return None

    fila = {"symbol": symbol, "fecha": a_fecha(tomar(CLAVES["fecha"]))}
    for k in ("open", "high", "low", "close", "change", "pct_change",
              "volume", "open_interest"):
        fila[k] = a_numero(tomar(CLAVES[k]))
    if fila["fecha"] is None or fila["close"] is None:
        return None
    fila["pct_change"] = _pct_a_porcentaje(
        fila["pct_change"], fila["change"], fila["close"])
    return fila


def _listas_de_dicts(obj, acc):
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj):
            acc.append(obj)
        for x in obj:
            _listas_de_dicts(x, acc)
    elif isinstance(obj, dict):
        for v in obj.values():
            _listas_de_dicts(v, acc)
    return acc


def extraer_historico(payload, symbol):
    """Busca en cualquier JSON la lista mas larga de filas con fecha y cierre."""
    mejores = []
    for lista in _listas_de_dicts(payload, []):
        filas = [f for f in (normalizar_fila(x, symbol) for x in lista) if f]
        if len(filas) > len(mejores):
            mejores = filas
    vistos, unicas = set(), []
    for f in mejores:
        if f["fecha"] not in vistos:
            vistos.add(f["fecha"])
            unicas.append(f)
    return sorted(unicas, key=lambda f: f["fecha"])
