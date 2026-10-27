"""Validación de dígitos de control de NIF, NIE y CIF españoles."""

from __future__ import annotations

import re

_LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"
_LETRAS_CIF_CONTROL = "JABCDEFGHI"


def normalizar(nif: str) -> str:
    """Mayúsculas, sin espacios, guiones, puntos ni prefijo de país 'ES'."""
    s = re.sub(r"[\s\-\.]", "", nif or "").upper()
    if s.startswith("ES") and len(s) == 11:
        s = s[2:]
    return s


def _valida_dni(s: str) -> bool:
    return bool(re.fullmatch(r"\d{8}[A-Z]", s)) and _LETRAS_DNI[int(s[:8]) % 23] == s[8]


def _valida_nie(s: str) -> bool:
    if not re.fullmatch(r"[XYZ]\d{7}[A-Z]", s):
        return False
    numero = str("XYZ".index(s[0])) + s[1:8]
    return _LETRAS_DNI[int(numero) % 23] == s[8]


def _valida_cif(s: str) -> bool:
    if not re.fullmatch(r"[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]", s):
        return False
    digitos = s[1:8]
    pares = sum(int(digitos[i]) for i in (1, 3, 5))
    impares = 0
    for i in (0, 2, 4, 6):
        doble = int(digitos[i]) * 2
        impares += doble // 10 + doble % 10
    control = (10 - (pares + impares) % 10) % 10
    letra = _LETRAS_CIF_CONTROL[control]
    if s[0] in "PQRSNW":
        return s[8] == letra
    if s[0] in "ABEH":
        return s[8] == str(control)
    return s[8] in (str(control), letra)


def tipo(nif: str) -> str | None:
    """'DNI', 'NIE', 'CIF' o None si el identificador no es válido."""
    s = normalizar(nif)
    if _valida_dni(s):
        return "DNI"
    if _valida_nie(s):
        return "NIE"
    if _valida_cif(s):
        return "CIF"
    return None


def es_valido(nif: str) -> bool:
    return tipo(nif) is not None


def parece_extranjero(nif: str) -> bool:
    """NIF-IVA con prefijo de otro país de la UE (p. ej. 'FR123...', 'DE123...')."""
    s = re.sub(r"[\s\-\.]", "", nif or "").upper()
    return bool(re.fullmatch(r"[A-Z]{2}[0-9A-Z]{2,13}", s)) and not s.startswith("ES") and tipo(s) is None
