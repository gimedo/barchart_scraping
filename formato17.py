"""
Formato de 17 columnas de la tabla de precios futuros (igual que el historial previo).

Columnas: symbol, last_price, price_change, open_price, high_price, low_price,
previous_price, volume, open_interest, fecha_reporte, fecha_hora_obtencion,
mes_anio, contract, contract_month, contract_year, mes_adelante, mes
"""
import re

COLUMNAS = [
    "symbol", "last_price", "price_change", "open_price", "high_price",
    "low_price", "previous_price", "volume", "open_interest", "fecha_reporte",
    "fecha_hora_obtencion", "mes_anio", "contract", "contract_month",
    "contract_year", "mes_adelante", "mes",
]

SYMBOL_RE = re.compile(r"^(.+?)([FGHJKMNQUVXZ])(\d{2})$")
MES_EN = {"F": "Jan", "G": "Feb", "H": "Mar", "J": "Apr", "K": "May", "M": "Jun",
          "N": "Jul", "Q": "Aug", "U": "Sep", "V": "Oct", "X": "Nov", "Z": "Dec"}
MES_NUM = {k: i + 1 for i, k in enumerate("FGHJKMNQUVXZ")}
MES_ES = {"Jan": "ene", "Feb": "feb", "Mar": "mar", "Apr": "abr", "May": "may",
          "Jun": "jun", "Jul": "jul", "Aug": "ago", "Sep": "sep", "Oct": "oct",
          "Nov": "nov", "Dec": "dic"}

# Desfase de mes_adelante por raiz. Con las capturas de 2026 (RB y HO = +1) cuadra;
# el historial de 2015 usa 0 para todas. Ajustalo si la regla actual es otra.
MES_ADELANTE_OFFSET = {"RB": 1, "HO": 1}


def campos_derivados(symbol, fecha_ref):
    """Devuelve mes_anio, contract, contract_month, contract_year, mes_adelante, mes.
    fecha_ref: datetime.date de referencia (fecha_reporte). None si el simbolo no es valido."""
    m = SYMBOL_RE.match(symbol or "")
    if not m:
        return None
    raiz, letra, yy = m.groups()
    mes_en = MES_EN[letra]
    meses = (2000 + int(yy) - fecha_ref.year) * 12 + MES_NUM[letra] - fecha_ref.month
    return {
        "mes_anio": f"{mes_en} '{yy}",
        "contract": raiz,
        "contract_month": letra,
        "contract_year": yy,
        "mes_adelante": meses + MES_ADELANTE_OFFSET.get(raiz, 0),
        "mes": MES_ES[mes_en],
    }
