"""Verificación cruzada: los datos que aporta el agente deben aparecer en el PDF.

Sirve para detectar lecturas erróneas o inventadas del LLM. Solo funciona con PDFs
que tienen capa de texto; con escaneados devuelve 'sin_texto'.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from . import nif as nifmod
from .importes import redondear
from .modelos import Factura


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for bloque in iter(lambda: fh.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def extraer_texto(path: Path) -> str:
    import logging

    from pypdf import PdfReader

    logging.getLogger("pypdf").setLevel(logging.ERROR)  # avisos de fuentes irrelevantes para el texto
    try:
        lector = PdfReader(str(path))
        return "\n".join((p.extract_text() or "") for p in lector.pages)
    except Exception:  # PDF dañado o cifrado: se trata como sin texto
        return ""


def _compacto(s: str) -> str:
    return re.sub(r"[\s\-\./]", "", s).upper()


def _variantes_importe(x: Decimal) -> set[str]:
    """Formas habituales de escribir un importe: 1234,56 · 1.234,56 · 1234.56 · 1,234.56 · 1 234,56."""
    entero, dec = f"{redondear(abs(x)):.2f}".split(".")
    miles = f"{int(entero):,}"  # separador ','
    return {
        f"{entero},{dec}",
        f"{entero}.{dec}",
        f"{miles.replace(',', '.')},{dec}",
        f"{miles}.{dec}",
        f"{miles.replace(',', ' ')},{dec}",
    }


def aparece_importe(texto: str, x: Decimal) -> bool:
    """¿Aparece el importe en el texto, en alguna de sus formas habituales?"""
    return _aparece_importe(re.sub(r"\s+", " ", texto), x)


def _aparece_importe(texto: str, x: Decimal) -> bool:
    for v in _variantes_importe(x):
        patron = r"(?<![\d.,])" + re.escape(v) + r"(?!\d)"
        if re.search(patron, texto):
            return True
    return False


@dataclass
class Verificacion:
    estado: str  # 'ok' | 'no_coincide' | 'sin_texto'
    no_encontrados: list[str] = field(default_factory=list)


def verificar(f: Factura, texto: str) -> Verificacion:
    if len(texto.strip()) < 20:
        return Verificacion("sin_texto")
    plano = re.sub(r"\s+", " ", texto)
    compacto = _compacto(texto)
    faltan: list[str] = []
    if _compacto(f.numero) not in compacto:
        faltan.append(f"número de factura '{f.numero}'")
    for etiqueta, valor in (("NIF del emisor", f.nif_emisor), ("NIF del receptor", f.nif_receptor)):
        if valor and nifmod.normalizar(valor) not in compacto:
            faltan.append(f"{etiqueta} '{valor}'")
    importes = [("total", f.total), ("cuota de IVA", f.cuota_total), ("base imponible", f.base_total)]
    for etiqueta, valor in importes:
        if valor and not _aparece_importe(plano, valor):
            # Facturas con varias líneas pueden no mostrar la suma: probamos línea a línea.
            if etiqueta == "base imponible" and all(_aparece_importe(plano, l.base) for l in f.lineas):
                continue
            if etiqueta == "cuota de IVA" and all(_aparece_importe(plano, l.cuota) for l in f.lineas):
                continue
            faltan.append(f"{etiqueta} {valor}")
    return Verificacion("ok" if not faltan else "no_coincide", faltan)
