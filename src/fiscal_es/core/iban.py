"""Validación de IBAN (ISO 13616, módulo 97)."""

from __future__ import annotations

import re


def normalizar(iban: str) -> str:
    return re.sub(r"\s+", "", iban or "").upper()


def es_valido(iban: str) -> bool:
    s = normalizar(iban)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", s):
        return False
    if s.startswith("ES") and len(s) != 24:
        return False
    reordenado = s[4:] + s[:4]
    numero = "".join(str(int(c, 36)) for c in reordenado)
    return int(numero) % 97 == 1
