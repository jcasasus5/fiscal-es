"""Generación de ficheros importables en la Sede (formato BOE) a partir del diseño oficial.

Común a todos los modelos (303, 390…). Las posiciones, longitudes, tipos y constantes
salen del Excel de la AEAT. Cada modelo solo declara cómo identificar los campos que
rellena (por número de casilla o por un patrón sobre la descripción) y qué páginas emite.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

from .diseno import Campo, Diseno, Pagina

ENCODING = "iso-8859-1"

# Campos estructurales: llevan constante o van en blanco.
_ESTRUCTURALES = (
    r"^Inicio del identificador",
    r"^Modelo\.?$",
    r"^P[aá]gina\.?$",
    r"^Fin de identificador",
    r"^Inden?tificador de fin de registro",
    r"^Reservado",
    r"^Constante",
    r"^Discriminante",
    r"^Tipo y cierre",
)


class ErrorDiseno(ValueError):
    """El diseño de registro no encaja con lo que sabe rellenar la herramienta."""


@dataclass
class EspecModelo:
    """Lo que la herramienta sabe de un modelo, aparte de su diseño."""

    modelo: str
    # Campos que rellenamos y no tienen casilla: página -> clave -> patrón sobre la descripción.
    semanticos: dict[str, dict[str, str]]
    # Páginas que se incluyen en el fichero, en orden.
    paginas: tuple[str, ...]
    # Campos sin casilla que conocemos y dejamos con su valor por defecto (blancos/ceros).
    conocidos: dict[str, tuple[str, ...]] = field(default_factory=dict)


def _es_estructural(c: Campo) -> bool:
    return any(re.search(p, c.descripcion, re.I) for p in _ESTRUCTURALES)


def asignar(pagina: Pagina, espec: EspecModelo) -> dict[str, list[Campo]]:
    """Identifica los campos de una página: clave semántica o '[casilla]' -> campos.

    Una casilla puede aparecer más de una vez en la misma página (p. ej. la página 6 del 390
    repite [84] en dos secciones): la primera aparición es '[84]', la segunda '[84]#2', etc.
    Falla si algún campo no se reconoce o si alguno de los que necesitamos no aparece.
    """
    patrones = espec.semanticos.get(pagina.codigo, {})
    conocidos = espec.conocidos.get(pagina.codigo, ())
    res: dict[str, list[Campo]] = {}
    desconocidos: list[str] = []
    for c in pagina.campos:
        claves = [k for k, p in patrones.items() if re.search(p, c.descripcion, re.I)]
        if len(claves) > 1:
            raise ErrorDiseno(f"Página {pagina.codigo}: el campo '{c.descripcion}' encaja con varias claves {claves}.")
        if claves:
            if claves[0] in res:
                raise ErrorDiseno(f"Página {pagina.codigo}: la clave {claves[0]} aparece repetida.")
            res[claves[0]] = [c]
        elif c.casilla:
            clave, n = f"[{c.casilla}]", 1
            while clave in res:
                n += 1
                clave = f"[{c.casilla}]#{n}"
            res[clave] = [c]
        elif not (_es_estructural(c) or c.constante is not None or any(re.search(p, c.descripcion, re.I) for p in conocidos)):
            desconocidos.append(f"{c.num}: {c.descripcion}")
    faltan = [k for k in patrones if k not in res]
    if desconocidos or faltan:
        partes = []
        if desconocidos:
            partes.append("campos desconocidos: " + "; ".join(desconocidos))
        if faltan:
            partes.append("campos esperados que no aparecen: " + ", ".join(faltan))
        raise ErrorDiseno(f"Modelo {espec.modelo}, página {pagina.codigo}: " + " | ".join(partes))
    return res


def campo(pagina: Pagina, espec: EspecModelo, clave: str) -> Campo:
    return asignar(pagina, espec)[clave][0]


def texto_aeat(s: str) -> str:
    """Mayúsculas, sin tildes (se conservan Ñ y Ç) y solo letras, números y blancos."""
    out = []
    for ch in s.upper():
        if ch in "ÑÇ":
            out.append(ch)
            continue
        out.append("".join(b for b in unicodedata.normalize("NFD", ch) if unicodedata.category(b) != "Mn"))
    s = re.sub(r"[^A-Z0-9ÑÇ ]", " ", "".join(out))  # An: solo letras, números y blancos
    return re.sub(r" +", " ", s).strip()


def formatear(c: Campo, valor: object) -> str:
    """Formatea un valor según el tipo y longitud del campo."""
    if c.lon is None:
        raise ErrorDiseno(f"El campo '{c.descripcion}' tiene longitud variable.")
    tipo = c.tipo.strip()
    if isinstance(valor, Decimal):
        if tipo not in ("Num", "N"):
            raise ErrorDiseno(f"Importe en un campo no numérico: {c.descripcion}")
        unidades = int((valor * (10 ** c.decimales)).to_integral_value())
        if unidades < 0:
            if tipo != "N":
                raise ErrorDiseno(f"Valor negativo en un campo sin signo: {c.descripcion}")
            s = "N" + str(-unidades).zfill(c.lon - 1)
        else:
            s = str(unidades).zfill(c.lon)
        if len(s) > c.lon:
            raise ErrorDiseno(f"El importe {valor} no cabe en {c.descripcion} ({c.lon} posiciones).")
        return s
    texto = "" if valor is None else str(valor)
    if tipo in ("Num", "N") and texto.strip() and not texto.isdigit():
        raise ErrorDiseno(f"Valor no numérico '{texto}' en {c.descripcion}")
    if len(texto) > c.lon:
        raise ErrorDiseno(f"El valor '{texto}' no cabe en {c.descripcion} ({c.lon} posiciones).")
    if tipo in ("Num", "N") and texto.isdigit():
        return texto.zfill(c.lon)
    return texto.ljust(c.lon)


def _valor_defecto(c: Campo) -> str:
    if c.constante is not None:
        return c.constante
    if c.tipo.strip() in ("Num", "N") and not _es_estructural(c):
        return "0" * (c.lon or 0)
    return ""


def render_pagina(pagina: Pagina, espec: EspecModelo, valores: dict[str, object]) -> str:
    asig = asignar(pagina, espec)
    por_campo = {id(c): k for k, cs in asig.items() for c in cs}
    sobrantes = set(valores) - set(asig)
    if sobrantes:
        raise ErrorDiseno(f"Página {pagina.codigo}: el diseño no tiene los campos {sorted(sobrantes)}.")
    partes: list[str] = []
    pos = 1
    for c in pagina.campos:
        if c.pos != pos:
            raise ErrorDiseno(f"Página {pagina.codigo}: el campo {c.num} empieza en {c.pos}, se esperaba {pos}.")
        clave = por_campo.get(id(c))
        if clave not in valores and c.constante is not None and c.lon is not None:
            # Las constantes del diseño van tal cual (la "Página" del 390 es Num pero vale "02B00").
            if len(c.constante) > c.lon:
                raise ErrorDiseno(f"Página {pagina.codigo}: la constante '{c.constante}' no cabe en {c.descripcion}.")
            s = c.constante.ljust(c.lon)
        else:
            s = formatear(c, valores[clave] if clave in valores else _valor_defecto(c))
        partes.append(s)
        pos += len(s)
    registro = "".join(partes)
    if pagina.total is not None and len(registro) != pagina.total:
        raise ErrorDiseno(f"Página {pagina.codigo}: longitud {len(registro)}, el diseño indica {pagina.total}.")
    return registro


_CABECERA = {
    "ejercicio": r"^Ejercicio de devengo",
    "periodo": r"^Per[ií]odo",
    "version_programa": r"^Versi[oó]n del Programa",
    "nif_desarrollo": r"^NIF Empresa Desarrollo",
    "contenido": r"^Contenido del fichero",
}


def generar(diseno: Diseno, espec: EspecModelo, valores: dict[str, dict[str, object]], *,
            ejercicio: int, periodo: str, nif: str, version_programa: str = "0100") -> bytes:
    """Fichero completo (ISO-8859-1, una sola línea, sin salto final)."""
    cuerpo = "".join(render_pagina(diseno.paginas[cod], espec, valores.get(cod, {})) for cod in espec.paginas)
    cab = diseno.paginas["00"]
    cab_espec = EspecModelo(espec.modelo, {"00": _CABECERA}, ())
    asig = asignar(cab, cab_espec)
    vals = {"ejercicio": str(ejercicio), "periodo": periodo, "version_programa": version_programa[:4], "nif_desarrollo": nif}
    partes = []
    for c in cab.campos:
        clave = next((k for k, cs in asig.items() if any(x is c for x in cs)), None)
        if clave == "contenido":
            partes.append(cuerpo)
        elif clave in vals:
            partes.append(formatear(c, vals[clave]))
        elif c.lon is None or c.pos is None:
            # Cierre: constante con marcadores del ejercicio (AAAA o EEEE) y del periodo (PP).
            cierre = (c.constante or "")
            for marca in ("AAAA", "EEEE"):
                cierre = cierre.replace(marca, str(ejercicio))
            cierre = cierre.replace("PP", periodo)
            if not cierre:
                raise ErrorDiseno(f"Cabecera: campo variable desconocido '{c.descripcion}'.")
            partes.append(cierre)
        else:
            partes.append(formatear(c, _valor_defecto(c)))
    return "".join(partes).encode(ENCODING)


def leer(diseno: Diseno, espec: EspecModelo, contenido: bytes) -> dict[str, dict[str, str]]:
    """Trocea un fichero generado según el diseño: página -> clave -> texto del campo."""
    texto = contenido.decode(ENCODING)
    res: dict[str, dict[str, str]] = {}
    for cod, pag in diseno.paginas.items():
        if cod == "00":
            continue
        marca = (pag.campos[0].constante or "") + espec.modelo + (pag.campos[2].constante or "") + ">"
        i = texto.find(marca)
        if i < 0:
            continue
        registro = texto[i : i + (pag.total or 0)]
        asig = asignar(pag, espec)
        res[cod] = {k: registro[cs[0].pos - 1 : cs[0].pos - 1 + cs[0].lon] for k, cs in asig.items()}
        res[cod]["__registro__"] = registro
    return res


def compatibilidad(d: Diseno, espec: EspecModelo) -> dict[str, object]:
    """¿Sabe la herramienta rellenar este diseño? Prueba a identificar todos los campos."""
    problemas = []
    for cod in ("00", *espec.paginas):
        if cod not in d.paginas:
            problemas.append(f"Falta la página {cod}.")
            continue
        try:
            if cod == "00":
                asignar(d.paginas[cod], EspecModelo(espec.modelo, {"00": _CABECERA}, ()))
            else:
                asignar(d.paginas[cod], espec)
        except ErrorDiseno as e:
            problemas.append(str(e))
    return {"compatible": not problemas, "problemas": problemas}
