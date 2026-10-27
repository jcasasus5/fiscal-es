"""Rutas de datos. Todo lo personal vive fuera del repo, en FISCAL_DATA_DIR."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Rutas:
    base: Path

    @property
    def db(self) -> Path:
        return self.base / "libro.db"

    @property
    def perfil(self) -> Path:
        return self.base / "perfil.json"

    @property
    def disenos(self) -> Path:
        return self.base / "disenos"

    @property
    def salida(self) -> Path:
        return self.base / "303"

    def preparar(self) -> "Rutas":
        for d in (self.base, self.disenos, self.salida):
            d.mkdir(parents=True, exist_ok=True)
        return self


DEFECTO = Path.home() / "fiscal-data"


def _desde_entorno() -> Path:
    """FISCAL_DATA_DIR, o ~/fiscal-data si no está definida.

    Algunos agentes no expanden `${VAR:-defecto}` en su configuración MCP y pasan el
    texto literal; en ese caso (o con valores relativos) se usa el directorio por defecto
    en lugar de crear una carpeta con un nombre extraño.
    """
    valor = (os.environ.get("FISCAL_DATA_DIR") or "").strip()
    if not valor or "${" in valor or "$" == valor[:1]:
        return DEFECTO
    ruta = Path(valor).expanduser()
    return ruta if ruta.is_absolute() else DEFECTO


def rutas(base: str | Path | None = None) -> Rutas:
    ruta = Path(base).expanduser() if base is not None else _desde_entorno()
    return Rutas(ruta).preparar()
