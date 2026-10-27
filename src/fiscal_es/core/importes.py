"""Importes con Decimal. Nunca float para dinero."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
CERO = Decimal("0")


def redondear(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def parse_importe(valor: object) -> Decimal:
    """Convierte números o textos ('1.234,56', '1234.56', '1,234.56', '63,00 €') a Decimal."""
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, bool) or valor is None:
        raise ValueError(f"Importe no válido: {valor!r}")
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        return Decimal(repr(valor))
    s = re.sub(r"[\s€]|EUR", "", str(valor), flags=re.IGNORECASE)
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation as e:
        raise ValueError(f"Importe no válido: {valor!r}") from e


def formato_es(x: Decimal) -> str:
    """1234.5 -> '1.234,50'."""
    signo = "-" if x < 0 else ""
    entero, dec = f"{abs(redondear(x)):.2f}".split(".")
    grupos = []
    while entero:
        grupos.insert(0, entero[-3:])
        entero = entero[:-3]
    return f"{signo}{'.'.join(grupos)},{dec}"
