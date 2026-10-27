"""Periodos trimestrales del 303 y plazos de presentación."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

_RE = re.compile(r"^\s*(\d{4})\s*[-/ ]?\s*([1-4])\s*T\s*$", re.IGNORECASE)
_RE_INV = re.compile(r"^\s*([1-4])\s*T\s*[-/ ]?\s*(\d{4})\s*$", re.IGNORECASE)


@dataclass(frozen=True, order=True)
class Trimestre:
    ejercicio: int
    numero: int  # 1..4

    @classmethod
    def parse(cls, texto: str) -> "Trimestre":
        """Acepta '2027-1T', '2027 1T', '1T-2027', '1T 2027'."""
        m = _RE.match(texto)
        if m:
            return cls(int(m.group(1)), int(m.group(2)))
        m = _RE_INV.match(texto)
        if m:
            return cls(int(m.group(2)), int(m.group(1)))
        raise ValueError(f"Trimestre no válido: {texto!r}. Usa el formato '2027-1T'.")

    @classmethod
    def de_fecha(cls, d: date) -> "Trimestre":
        return cls(d.year, (d.month - 1) // 3 + 1)

    def __str__(self) -> str:
        return f"{self.ejercicio}-{self.numero}T"

    @property
    def codigo(self) -> str:
        """Código de periodo del diseño de registro: '1T'..'4T'."""
        return f"{self.numero}T"

    @property
    def inicio(self) -> date:
        return date(self.ejercicio, 3 * (self.numero - 1) + 1, 1)

    @property
    def fin(self) -> date:
        siguiente = self.siguiente().inicio
        return siguiente - timedelta(days=1)

    @property
    def es_ultimo(self) -> bool:
        return self.numero == 4

    def contiene(self, d: date) -> bool:
        return self.inicio <= d <= self.fin

    def siguiente(self) -> "Trimestre":
        if self.numero == 4:
            return Trimestre(self.ejercicio + 1, 1)
        return Trimestre(self.ejercicio, self.numero + 1)

    def anterior(self) -> "Trimestre":
        if self.numero == 1:
            return Trimestre(self.ejercicio - 1, 4)
        return Trimestre(self.ejercicio, self.numero - 1)


def _domingo_pascua(anio: int) -> date:
    # Algoritmo de Meeus/Jones/Butcher (calendario gregoriano).
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(anio, mes, dia)


def festivos_nacionales(anio: int) -> set[date]:
    """Festivos nacionales comunes. No incluye festivos autonómicos ni locales."""
    fijos = [(1, 1), (1, 6), (5, 1), (8, 15), (10, 12), (11, 1), (12, 6), (12, 8), (12, 25)]
    dias = {date(anio, m, d) for m, d in fijos}
    dias.add(_domingo_pascua(anio) - timedelta(days=2))  # Viernes Santo
    return dias


def _habil(d: date) -> date:
    while d.weekday() >= 5 or d in festivos_nacionales(d.year):
        d += timedelta(days=1)
    return d


@dataclass(frozen=True)
class Plazo:
    trimestre: Trimestre
    inicio: date
    fin: date
    fin_domiciliacion: date


def plazo_303(t: Trimestre) -> Plazo:
    """Plazo de presentación del 303 trimestral.

    1T-3T: del 1 al 20 del mes siguiente. 4T: del 1 al 30 de enero.
    Si el último día es inhábil se traslada al siguiente hábil (solo se tienen
    en cuenta fines de semana y festivos nacionales). La domiciliación termina
    5 días naturales antes del último día ordinario (el 15, o el 25 de enero).
    """
    sig = t.siguiente().inicio
    nominal = date(sig.year, sig.month, 30 if t.es_ultimo else 20)
    return Plazo(t, sig, _habil(nominal), nominal - timedelta(days=5))


def proximos_plazos(hoy: date, n: int = 2) -> list[Plazo]:
    """Plazos cuyo fin aún no ha pasado, empezando por el más cercano."""
    t = Trimestre.de_fecha(hoy).anterior()
    res: list[Plazo] = []
    while len(res) < n:
        p = plazo_303(t)
        if p.fin >= hoy:
            res.append(p)
        t = t.siguiente()
    return res
