"""Comprobación e instalación del diseño de registro vigente publicado por la AEAT.

Es la única parte con acceso a red, y solo a `sede.agenciatributaria.gob.es` para
descargar información pública. Nunca se envía ningún dato fiscal.
"""

from __future__ import annotations

import html
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from . import diseno as dmod
from .aeat import get as _get
from .periodo import Trimestre

PAGINA_DISENOS = "https://sede.agenciatributaria.gob.es/Sede/ayuda/disenos-registro/modelos-300-399.html"


@dataclass
class Publicado:
    url: str
    archivo: str
    texto: str
    ejercicio_desde: int | None
    actualizado: date | None
    modelo: str = "303"

    @property
    def desde(self) -> str:
        return f"{self.ejercicio_desde}-1T" if self.ejercicio_desde else ""


def _ejercicio_archivo(archivo: str) -> int | None:
    """DR303e26v101.xlsx -> 2026; dr390e2026.xlsx -> 2026."""
    mm = re.search(r"DR\d{3}e(\d{4}|\d{2})", archivo, re.I)
    if not mm:
        return None
    n = int(mm.group(1))
    return n if n > 999 else 2000 + n


def especificacion(modelo: str):
    from . import fichero303, fichero390

    especs = {"303": fichero303.ESPEC, "390": fichero390.ESPEC}
    if modelo not in especs:
        raise ValueError(f"Modelo no soportado: {modelo}")
    return especs[modelo]


def parsear_pagina(html_texto: str, base: str = PAGINA_DISENOS, modelo: str = "303") -> list[Publicado]:
    """Enlaces a diseños del modelo en la página de la AEAT."""
    res = []
    for m in re.finditer(rf'<a[^>]+href="([^"]*DR{modelo}[^"]*\.xlsx)"[^>]*>(.*?)</a>', html_texto, re.I | re.S):
        href, interior = m.group(1), m.group(2)
        texto = html.unescape(re.sub(r"<[^>]+>", " ", interior))
        texto = re.sub(r"\s+", " ", texto).strip()
        ej = re.search(r"Ejercicio\s+(\d{4})", texto, re.I)
        act = re.search(r"actualizado\s+(\d{1,2})/(\d{1,2})/(\d{2,4})", texto, re.I)
        actualizado = None
        if act:
            d, mth, y = (int(x) for x in act.groups())
            actualizado = date(y + 2000 if y < 100 else y, mth, d)
        ejercicio = int(ej.group(1)) if ej else None
        archivo = href.rsplit("/", 1)[-1]
        if ejercicio is None:
            ejercicio = _ejercicio_archivo(archivo)
        res.append(Publicado(urljoin(base, href), archivo, texto, ejercicio, actualizado, modelo))
    return res


def consultar_publicados(modelo: str = "303") -> list[Publicado]:
    return parsear_pagina(_get(PAGINA_DISENOS).decode("utf-8", errors="replace"), modelo=modelo)


def descargar(pub: Publicado, destino_dir: Path) -> Path:
    destino_dir.mkdir(parents=True, exist_ok=True)
    datos = _get(pub.url)
    tmp = Path(tempfile.mkstemp(suffix=".xlsx", dir=destino_dir)[1])
    tmp.write_bytes(datos)
    return tmp


def comprobar(t: Trimestre, dir_usuario: Path, publicados: list[Publicado] | None = None,
              modelo: str = "303") -> dict[str, Any]:
    """Compara el diseño publicado aplicable a `t` con el instalado.

    Descarga el Excel a una carpeta temporal para comparar su hash y su contenido.
    No instala nada.
    """
    if publicados is None:
        publicados = consultar_publicados(modelo)
    aplicables = [p for p in publicados if p.ejercicio_desde and Trimestre(p.ejercicio_desde, 1) <= t]
    try:
        instalado = dmod.seleccionar(t, dir_usuario, modelo)
    except LookupError:
        instalado = None
    if not aplicables:
        return {
            "estado": "sin_publicado",
            "mensaje": f"La AEAT no publica ningún diseño aplicable a {t} (¿periodo anterior a los publicados?).",
            "instalado": instalado.entrada.archivo if instalado else None,
        }
    pub = max(aplicables, key=lambda p: (p.ejercicio_desde, p.actualizado or date.min))
    tmpdir = Path(tempfile.mkdtemp(prefix=f"dr{modelo}-"))
    try:
        ruta = descargar(pub, tmpdir)
        sha = dmod.sha256_de(ruta)
        info = {
            "publicado": {"archivo": pub.archivo, "url": pub.url, "texto": pub.texto,
                          "actualizado": pub.actualizado.isoformat() if pub.actualizado else None, "sha256": sha},
            "instalado": None,
        }
        if instalado:
            info["instalado"] = {"archivo": instalado.entrada.archivo, "origen": instalado.origen,
                                 "sha256": instalado.entrada.sha256}
        if instalado and instalado.entrada.sha256 == sha:
            info.update(estado="al_dia", mensaje=f"El diseño instalado ({pub.archivo}) es el vigente.")
            return info
        nuevo = dmod.leer_xlsx(ruta, modelo)
        if instalado:
            info["diferencias"] = dmod.diferencias(dmod.cargar(instalado), nuevo)
        info["compatibilidad"] = compatibilidad(nuevo)
        info.update(
            estado="nuevo",
            mensaje=f"Hay un diseño publicado distinto del instalado: {pub.archivo}. Instálalo con instalar_diseno_{modelo}.",
        )
        return info
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def compatibilidad(d: dmod.Diseno) -> dict[str, Any]:
    """¿Sabe la herramienta rellenar este diseño? Prueba a identificar todos los campos."""
    from .fichero import compatibilidad as _compat

    return _compat(d, especificacion(d.modelo))


def instalar(dir_usuario: Path, pub: Publicado | None = None, ruta_local: Path | None = None,
             desde: str | None = None, modelo: str | None = None) -> dict[str, Any]:
    """Instala un diseño en FISCAL_DATA_DIR/disenos, desde la AEAT o desde un .xlsx local."""
    dir_usuario.mkdir(parents=True, exist_ok=True)
    if ruta_local is not None:
        origen = Path(ruta_local)
        archivo, fuente, actualizado = origen.name, str(origen), None
        tmp = dir_usuario / f".tmp-{archivo}"
        shutil.copyfile(origen, tmp)
    elif pub is not None:
        tmp = descargar(pub, dir_usuario)
        archivo, fuente = pub.archivo, pub.url
        actualizado = pub.actualizado.isoformat() if pub.actualizado else None
        desde = desde or pub.desde
    else:
        raise ValueError("Indica la publicación de la AEAT o la ruta a un .xlsx local.")
    try:
        nuevo = dmod.leer_xlsx(tmp, modelo or (pub.modelo if pub else None))
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    if not desde:
        ej = _ejercicio_archivo(archivo)
        if not ej:
            tmp.unlink(missing_ok=True)
            raise ValueError("No se puede deducir desde qué periodo aplica el diseño: indica 'desde' (p. ej. 2027-1T).")
        desde = f"{ej}-1T"
    Trimestre.parse(desde)
    sha = dmod.sha256_de(tmp)
    # El nombre incluye parte del hash: la AEAT puede republicar un fichero con el mismo nombre.
    destino = dir_usuario / f"{Path(archivo).stem}-{sha[:8]}.xlsx"
    tmp.replace(destino)
    entradas = [e for e in dmod.leer_manifiesto(dir_usuario) if e.sha256 != sha]
    entrada = dmod.EntradaManifiesto(
        archivo=destino.name, desde=desde, actualizado=actualizado, sha256=sha, fuente=fuente,
        instalado=datetime.now(timezone.utc).isoformat(timespec="seconds"), modelo=nuevo.modelo,
    )
    entradas.append(entrada)
    dmod.escribir_manifiesto(dir_usuario, entradas)
    return {"instalado": destino.name, "modelo": nuevo.modelo, "desde": desde, "sha256": sha,
            "compatibilidad": compatibilidad(nuevo)}
