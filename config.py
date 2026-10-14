"""Configuracion del proyecto. Edita aqui, no en los scripts."""
import os

# Raices a seguir y cuantos vencimientos mensuales hacia adelante (desde el mes actual).
# Los simbolos se generan solos (p. ej. CLX26, CLZ26...), asi no hay que editar la lista
# cada mes. Si prefieres una lista fija, llena SIMBOLOS_HISTORICO (tiene prioridad).
RAICES = ["CL", "RB", "HO", "QA"]
MESES_ADELANTE = 6
SIMBOLOS_HISTORICO = []          # p. ej. ["CLX26", "HOX26"]

# Un contrato cuyo ultimo dato guardado tiene mas de estos dias de antiguedad se
# considera vencido y se omite en las siguientes corridas (usa --forzar para reintentar).
DIAS_PARA_VENCIDO = 10

# Modo del navegador. Se puede cambiar SIN editar el archivo con variables de entorno:
#   BARCHART_HEADLESS=true   -> sin ventana (lo mas simple en un servidor, pero puede ser detectado)
#   BARCHART_HEADLESS=false  -> con ventana (en un servidor sin pantalla: usar xvfb-run)
#   BARCHART_CDP_URL=http://127.0.0.1:9222 -> conectarse a un Chrome que ya esta abierto como servicio
HEADLESS = os.environ.get("BARCHART_HEADLESS", "false").lower() in ("1", "true", "yes", "si")
CDP_URL = os.environ.get("BARCHART_CDP_URL", "")

# Espera extra (milisegundos) tras cargar la pagina, para que terminen las peticiones
ESPERA_MS = 8000

# Pausa entre simbolos (segundos). No lo bajes: es una cortesia con el sitio.
PAUSA_ENTRE_SIMBOLOS = 5

# Que peticiones de fondo (XHR/fetch) se capturan. Es una REGEX sobre la URL.
XHR_PATRON = r"core-api"

DB_PATH = "barchart.db"
DEBUG_DIR = "debug"

# Pagina de historial de un contrato
URL_HISTORICO = "https://www.barchart.com/futures/quotes/{symbol}/price-history/historical"

# Endpoint de historial: PROBADO contra Barchart real (502 filas = 2 anios de datos diarios).
# La cuenta gratuita da hasta ~2 anios de historial diario.
API_HISTORICO = (
    "https://www.barchart.com/proxies/core-api/v1/historical/get"
    "?symbol={symbol}"
    "&fields=tradeTime,openPrice,highPrice,lowPrice,lastPrice,priceChange,"
    "percentChange,volume,openInterest"
    "&type=eod&orderBy=tradeTime&orderDir=desc"
    "&startDate={desde}&endDate={hasta}&limit={limite}&raw=1"
)
