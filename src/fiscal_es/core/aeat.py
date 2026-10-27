"""Acceso de solo lectura a páginas públicas de la Sede de la AEAT.

Única salida a red de la herramienta. Solo HTTPS y solo `sede.agenciatributaria.gob.es`.
Nunca se envía ningún dato del usuario: solo se descargan páginas y ficheros públicos.
"""

from __future__ import annotations

import hashlib
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

HOST_PERMITIDO = "sede.agenciatributaria.gob.es"
_UA = "fiscal-es (consulta de información pública de la AEAT)"


def get(url: str, timeout: float = 30) -> bytes:
    p = urlparse(url)
    if p.scheme != "https" or p.hostname != HOST_PERMITIDO:
        raise ValueError(f"Solo se permite descargar de https://{HOST_PERMITIDO}: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (host verificado)
        return r.read()


def get_cacheado(url: str, cache_dir: Path | None, max_edad_s: float = 7 * 86400) -> bytes:
    """Como `get`, pero guarda la respuesta en disco y la reutiliza durante `max_edad_s`."""
    if cache_dir is None:
        return get(url)
    cache_dir.mkdir(parents=True, exist_ok=True)
    f = cache_dir / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".html")
    if f.exists() and time.time() - f.stat().st_mtime < max_edad_s:
        return f.read_bytes()
    datos = get(url)
    f.write_bytes(datos)
    return datos
