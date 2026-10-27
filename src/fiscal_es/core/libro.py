"""Libro registro en SQLite: fuente de verdad, con deduplicación y trazabilidad.

Nada se borra. Cada alta, corrección, confirmación o descarte queda en `eventos`
con el estado anterior, el nuevo y el motivo.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal
from typing import Any

from . import nif as nifmod
from .modelos import NIVELES_BLOQUEANTES, Factura, Incidencia
from .periodo import Trimestre

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS facturas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,
    numero TEXT NOT NULL,
    numero_norm TEXT NOT NULL,
    nif_emisor_norm TEXT NOT NULL,
    fecha_devengo TEXT NOT NULL,
    trimestre TEXT NOT NULL,
    estado TEXT NOT NULL,              -- valida | pendiente | descartada
    datos TEXT NOT NULL,               -- Factura en JSON
    incidencias TEXT NOT NULL,         -- lista de Incidencia en JSON
    confirmada TEXT,                   -- motivo con el que el usuario aceptó avisos 'revisar'
    pdf_path TEXT,
    pdf_sha256 TEXT,
    verificacion_pdf TEXT,             -- ok | no_coincide | sin_texto | sin_pdf
    origen TEXT,
    creada TEXT NOT NULL,
    actualizada TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_factura ON facturas (tipo, nif_emisor_norm, numero_norm);
CREATE UNIQUE INDEX IF NOT EXISTS ux_pdf ON facturas (pdf_sha256) WHERE pdf_sha256 IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_trimestre ON facturas (trimestre);
CREATE TABLE IF NOT EXISTS autoliquidaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    modelo TEXT NOT NULL,              -- 303 | 390
    ejercicio INTEGER NOT NULL,
    periodo TEXT NOT NULL,             -- 1T..4T, o 0A para el 390
    estado TEXT NOT NULL,              -- generada | presentada | no_presentada
    tipo_declaracion TEXT,
    sin_actividad INTEGER,
    casillas TEXT NOT NULL,            -- {"07": "300.00", "71": "63.00", ...}
    justificante TEXT,
    fecha_presentacion TEXT,
    fichero TEXT,                      -- fichero generado por la herramienta, si lo hay
    pdf_path TEXT,                     -- copia del justificante, si lo hay
    pdf_sha256 TEXT,
    origen TEXT,
    motivo TEXT,
    creada TEXT NOT NULL,
    actualizada TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_autoliq_justificante ON autoliquidaciones (modelo, justificante)
    WHERE justificante IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_autoliq_periodo ON autoliquidaciones (modelo, ejercicio, periodo);
CREATE TABLE IF NOT EXISTS autoliq_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    autoliq_id INTEGER NOT NULL REFERENCES autoliquidaciones(id),
    ts TEXT NOT NULL,
    accion TEXT NOT NULL,              -- generada | regenerada | presentada | no_presentada
    antes TEXT,
    despues TEXT,
    motivo TEXT
);
CREATE TABLE IF NOT EXISTS eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    factura_id INTEGER NOT NULL REFERENCES facturas(id),
    ts TEXT NOT NULL,
    accion TEXT NOT NULL,              -- alta | correccion | confirmacion | descarte | reactivacion
    antes TEXT,
    despues TEXT,
    motivo TEXT
);
"""


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm_numero(numero: str) -> str:
    return "".join(c for c in numero.upper() if c.isalnum())


def estado_de(incidencias: list[Incidencia], confirmada: bool) -> str:
    niveles = {i.nivel for i in incidencias}
    if niveles & {"error", "fuera_alcance"}:
        return "pendiente"
    if "revisar" in niveles and not confirmada:
        return "pendiente"
    return "valida"


@dataclass
class Registro:
    id: int
    factura: Factura
    estado: str
    incidencias: list[Incidencia]
    confirmada: str | None
    pdf_path: str | None
    pdf_sha256: str | None
    verificacion_pdf: str | None
    origen: str | None

    def to_dict(self) -> dict[str, Any]:
        f = self.factura
        return {
            "id": self.id,
            "estado": self.estado,
            "tipo": f.tipo,
            "numero": f.numero,
            "fecha": f.fecha.isoformat(),
            "trimestre": str(f.trimestre),
            "emisor": f"{f.nombre_emisor} ({f.nif_emisor})".strip(),
            "receptor": f"{f.nombre_receptor or ''} ({f.nif_receptor or '-'})".strip(),
            "base": str(f.base_total),
            "cuota": str(f.cuota_total),
            "retencion_irpf": str(f.retencion_irpf),
            "total": str(f.total),
            "lineas": [{"base": str(l.base), "tipo_iva": str(l.tipo_iva), "cuota": str(l.cuota)} for l in f.lineas],
            "incidencias": [i.to_dict() for i in self.incidencias],
            "confirmada": self.confirmada,
            "verificacion_pdf": self.verificacion_pdf,
            "pdf": self.pdf_path,
            "origen": self.origen,
        }


class Duplicada(Exception):
    def __init__(self, existente: Registro, motivo: str):
        super().__init__(motivo)
        self.existente = existente
        self.motivo = motivo


class Libro:
    def __init__(self, path: Path | str):
        self.path = str(path)
        # El servidor MCP ejecuta las tools en hilos; el acceso se serializa con un lock allí.
        self.con = sqlite3.connect(self.path, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self.con.executescript(_ESQUEMA)

    def close(self) -> None:
        self.con.close()

    # --- lectura ---
    def _registro(self, row: sqlite3.Row) -> Registro:
        return Registro(
            id=row["id"],
            factura=Factura.from_dict(json.loads(row["datos"])),
            estado=row["estado"],
            incidencias=[Incidencia(**i) for i in json.loads(row["incidencias"])],
            confirmada=row["confirmada"],
            pdf_path=row["pdf_path"],
            pdf_sha256=row["pdf_sha256"],
            verificacion_pdf=row["verificacion_pdf"],
            origen=row["origen"],
        )

    def obtener(self, factura_id: int) -> Registro:
        row = self.con.execute("SELECT * FROM facturas WHERE id = ?", (factura_id,)).fetchone()
        if row is None:
            raise KeyError(f"No existe la factura con id {factura_id}")
        return self._registro(row)

    def listar(self, trimestre: Trimestre | None = None, estado: str | None = None) -> list[Registro]:
        sql, args = "SELECT * FROM facturas WHERE 1=1", []
        if trimestre:
            sql += " AND trimestre = ?"
            args.append(str(trimestre))
        if estado:
            sql += " AND estado = ?"
            args.append(estado)
        sql += " ORDER BY fecha_devengo, id"
        return [self._registro(r) for r in self.con.execute(sql, args)]

    def eventos(self, factura_id: int) -> list[dict[str, Any]]:
        rows = self.con.execute("SELECT * FROM eventos WHERE factura_id = ? ORDER BY id", (factura_id,))
        return [dict(r) for r in rows]

    def buscar_duplicada(self, f: Factura, pdf_sha256: str | None, excluir_id: int | None = None) -> tuple[Registro, str] | None:
        if pdf_sha256:
            row = self.con.execute("SELECT * FROM facturas WHERE pdf_sha256 = ?", (pdf_sha256,)).fetchone()
            if row is not None and row["id"] != excluir_id:
                return self._registro(row), "el mismo PDF ya está registrado"
        row = self.con.execute(
            "SELECT * FROM facturas WHERE tipo = ? AND nif_emisor_norm = ? AND numero_norm = ?",
            (f.tipo, nifmod.normalizar(f.nif_emisor), _norm_numero(f.numero)),
        ).fetchone()
        if row is not None and row["id"] != excluir_id:
            return self._registro(row), "ya hay una factura con el mismo número y emisor"
        return None

    # --- escritura (siempre con evento) ---
    def _evento(self, factura_id: int, accion: str, antes: Any, despues: Any, motivo: str | None) -> None:
        self.con.execute(
            "INSERT INTO eventos (factura_id, ts, accion, antes, despues, motivo) VALUES (?, ?, ?, ?, ?, ?)",
            (
                factura_id,
                _ahora(),
                accion,
                json.dumps(antes, ensure_ascii=False) if antes is not None else None,
                json.dumps(despues, ensure_ascii=False) if despues is not None else None,
                motivo,
            ),
        )

    def alta(
        self,
        f: Factura,
        incidencias: list[Incidencia],
        *,
        pdf_path: str | None = None,
        pdf_sha256: str | None = None,
        verificacion_pdf: str | None = None,
        origen: str | None = None,
    ) -> Registro:
        dup = self.buscar_duplicada(f, pdf_sha256)
        if dup:
            raise Duplicada(*dup)
        ahora = _ahora()
        estado = estado_de(incidencias, confirmada=False)
        with self.con:
            cur = self.con.execute(
                """INSERT INTO facturas (tipo, numero, numero_norm, nif_emisor_norm, fecha_devengo, trimestre,
                   estado, datos, incidencias, pdf_path, pdf_sha256, verificacion_pdf, origen, creada, actualizada)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f.tipo,
                    f.numero,
                    _norm_numero(f.numero),
                    nifmod.normalizar(f.nif_emisor),
                    f.fecha_devengo.isoformat(),
                    str(f.trimestre),
                    estado,
                    json.dumps(f.to_dict(), ensure_ascii=False),
                    json.dumps([i.to_dict() for i in incidencias], ensure_ascii=False),
                    pdf_path,
                    pdf_sha256,
                    verificacion_pdf,
                    origen,
                    ahora,
                    ahora,
                ),
            )
            fid = int(cur.lastrowid)
            self._evento(fid, "alta", None, f.to_dict(), origen)
        return self.obtener(fid)

    def actualizar(
        self,
        factura_id: int,
        f: Factura,
        incidencias: list[Incidencia],
        motivo: str,
        *,
        verificacion_pdf: str | None = None,
    ) -> Registro:
        if not motivo or not motivo.strip():
            raise ValueError("Toda corrección necesita un motivo.")
        previo = self.obtener(factura_id)
        if previo.estado == "descartada":
            raise ValueError("La factura está descartada; reactívala antes de corregirla.")
        dup = self.buscar_duplicada(f, None, excluir_id=factura_id)
        if dup:
            raise Duplicada(*dup)
        # Una corrección invalida la confirmación previa: hay que volver a revisar.
        estado = estado_de(incidencias, confirmada=False)
        with self.con:
            self.con.execute(
                """UPDATE facturas SET tipo=?, numero=?, numero_norm=?, nif_emisor_norm=?, fecha_devengo=?,
                   trimestre=?, estado=?, datos=?, incidencias=?, confirmada=NULL,
                   verificacion_pdf=COALESCE(?, verificacion_pdf), actualizada=? WHERE id=?""",
                (
                    f.tipo,
                    f.numero,
                    _norm_numero(f.numero),
                    nifmod.normalizar(f.nif_emisor),
                    f.fecha_devengo.isoformat(),
                    str(f.trimestre),
                    estado,
                    json.dumps(f.to_dict(), ensure_ascii=False),
                    json.dumps([i.to_dict() for i in incidencias], ensure_ascii=False),
                    verificacion_pdf,
                    _ahora(),
                    factura_id,
                ),
            )
            self._evento(factura_id, "correccion", previo.factura.to_dict(), f.to_dict(), motivo)
        return self.obtener(factura_id)

    def confirmar(self, factura_id: int, motivo: str) -> Registro:
        """Acepta los avisos de nivel 'revisar'. Errores y fuera de alcance no se pueden confirmar."""
        if not motivo or not motivo.strip():
            raise ValueError("La confirmación necesita un motivo.")
        r = self.obtener(factura_id)
        if r.estado == "descartada":
            raise ValueError("La factura está descartada.")
        bloqueos = [i for i in r.incidencias if i.nivel in ("error", "fuera_alcance")]
        if bloqueos:
            raise ValueError(
                "No se puede confirmar: tiene incidencias que hay que corregir, no aceptar: "
                + "; ".join(i.mensaje for i in bloqueos)
            )
        with self.con:
            self.con.execute(
                "UPDATE facturas SET estado='valida', confirmada=?, actualizada=? WHERE id=?",
                (motivo, _ahora(), factura_id),
            )
            self._evento(factura_id, "confirmacion", r.estado, "valida", motivo)
        return self.obtener(factura_id)

    def descartar(self, factura_id: int, motivo: str) -> Registro:
        if not motivo or not motivo.strip():
            raise ValueError("Descartar una factura necesita un motivo.")
        r = self.obtener(factura_id)
        with self.con:
            self.con.execute(
                "UPDATE facturas SET estado='descartada', actualizada=? WHERE id=?", (_ahora(), factura_id)
            )
            self._evento(factura_id, "descarte", r.estado, "descartada", motivo)
        return self.obtener(factura_id)

    def reactivar(self, factura_id: int, motivo: str) -> Registro:
        r = self.obtener(factura_id)
        if r.estado != "descartada":
            raise ValueError("La factura no está descartada.")
        estado = estado_de(r.incidencias, confirmada=bool(r.confirmada))
        with self.con:
            self.con.execute(
                "UPDATE facturas SET estado=?, actualizada=? WHERE id=?", (estado, _ahora(), factura_id)
            )
            self._evento(factura_id, "reactivacion", "descartada", estado, motivo)
        return self.obtener(factura_id)


@dataclass
class Autoliquidacion:
    id: int
    modelo: str
    ejercicio: int
    periodo: str
    estado: str
    tipo_declaracion: str | None
    sin_actividad: bool | None
    casillas: dict[str, Decimal]
    justificante: str | None
    fecha_presentacion: str | None
    fichero: str | None
    pdf_path: str | None
    origen: str | None
    motivo: str | None

    def casilla(self, c: str) -> Decimal:
        return self.casillas.get(c, Decimal("0"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "modelo": self.modelo,
            "ejercicio": self.ejercicio,
            "periodo": self.periodo,
            "estado": self.estado,
            "tipo_declaracion": self.tipo_declaracion,
            "sin_actividad": self.sin_actividad,
            "casillas": {k: str(v) for k, v in sorted(self.casillas.items(), key=lambda kv: int(kv[0])) if v},
            "justificante": self.justificante,
            "fecha_presentacion": self.fecha_presentacion,
            "fichero": self.fichero,
            "justificante_pdf": self.pdf_path,
            "origen": self.origen,
            "motivo": self.motivo,
        }


def _autoliq(row: sqlite3.Row) -> Autoliquidacion:
    return Autoliquidacion(
        id=row["id"],
        modelo=row["modelo"],
        ejercicio=row["ejercicio"],
        periodo=row["periodo"],
        estado=row["estado"],
        tipo_declaracion=row["tipo_declaracion"],
        sin_actividad=None if row["sin_actividad"] is None else bool(row["sin_actividad"]),
        casillas={k: Decimal(v) for k, v in json.loads(row["casillas"]).items()},
        justificante=row["justificante"],
        fecha_presentacion=row["fecha_presentacion"],
        fichero=row["fichero"],
        pdf_path=row["pdf_path"],
        origen=row["origen"],
        motivo=row["motivo"],
    )


class Autoliquidaciones:
    """Autoliquidaciones generadas o presentadas, guardadas junto al libro registro."""

    def __init__(self, libro: Libro):
        self.con = libro.con

    def _evento(self, aid: int, accion: str, antes: Any, despues: Any, motivo: str | None) -> None:
        self.con.execute(
            "INSERT INTO autoliq_eventos (autoliq_id, ts, accion, antes, despues, motivo) VALUES (?, ?, ?, ?, ?, ?)",
            (aid, _ahora(), accion,
             json.dumps(antes, ensure_ascii=False) if antes is not None else None,
             json.dumps(despues, ensure_ascii=False) if despues is not None else None, motivo),
        )

    def obtener(self, aid: int) -> Autoliquidacion:
        row = self.con.execute("SELECT * FROM autoliquidaciones WHERE id = ?", (aid,)).fetchone()
        if row is None:
            raise KeyError(f"No existe la autoliquidación {aid}")
        return _autoliq(row)

    def listar(self, modelo: str | None = None, ejercicio: int | None = None, periodo: str | None = None) -> list[Autoliquidacion]:
        sql, args = "SELECT * FROM autoliquidaciones WHERE 1=1", []
        for col, v in (("modelo", modelo), ("ejercicio", ejercicio), ("periodo", periodo)):
            if v is not None:
                sql += f" AND {col} = ?"
                args.append(v)
        return [_autoliq(r) for r in self.con.execute(sql + " ORDER BY ejercicio, periodo, id", args)]

    def eventos(self, aid: int) -> list[dict[str, Any]]:
        return [dict(r) for r in self.con.execute("SELECT * FROM autoliq_eventos WHERE autoliq_id = ? ORDER BY id", (aid,))]

    @staticmethod
    def _casillas_json(casillas: dict[str, Decimal]) -> str:
        return json.dumps({k: str(v) for k, v in casillas.items()}, ensure_ascii=False)

    def guardar_generada(self, modelo: str, ejercicio: int, periodo: str, casillas: dict[str, Decimal],
                         tipo: str | None, sin_actividad: bool | None, fichero: str) -> Autoliquidacion:
        """Guarda (o sustituye) la versión generada por la herramienta que aún no consta como presentada."""
        ahora = _ahora()
        previa = next((a for a in self.listar(modelo, ejercicio, periodo) if a.estado == "generada"), None)
        with self.con:
            if previa:
                self.con.execute(
                    "UPDATE autoliquidaciones SET casillas=?, tipo_declaracion=?, sin_actividad=?, fichero=?, actualizada=? WHERE id=?",
                    (self._casillas_json(casillas), tipo, sin_actividad, fichero, ahora, previa.id),
                )
                self._evento(previa.id, "regenerada", previa.to_dict()["casillas"], {k: str(v) for k, v in casillas.items()}, None)
                aid = previa.id
            else:
                cur = self.con.execute(
                    """INSERT INTO autoliquidaciones (modelo, ejercicio, periodo, estado, tipo_declaracion, sin_actividad,
                       casillas, fichero, origen, creada, actualizada) VALUES (?, ?, ?, 'generada', ?, ?, ?, ?, 'fiscal-es', ?, ?)""",
                    (modelo, ejercicio, periodo, tipo, sin_actividad, self._casillas_json(casillas), fichero, ahora, ahora),
                )
                aid = int(cur.lastrowid)
                self._evento(aid, "generada", None, {k: str(v) for k, v in casillas.items()}, None)
        return self.obtener(aid)

    def registrar_presentada(self, modelo: str, ejercicio: int, periodo: str, casillas: dict[str, Decimal],
                             tipo: str, sin_actividad: bool | None, justificante: str, fecha: str | None,
                             pdf_path: str | None, pdf_sha256: str | None, origen: str | None) -> tuple[Autoliquidacion, Autoliquidacion | None]:
        """Registra una autoliquidación presentada. Si había una generada para el mismo periodo,
        la convierte en presentada y devuelve también la versión generada para compararlas."""
        existente = self.con.execute(
            "SELECT * FROM autoliquidaciones WHERE modelo = ? AND justificante = ?", (modelo, justificante)
        ).fetchone()
        if existente is not None:
            raise ValueError(f"El justificante {justificante} ya está registrado (autoliquidación {existente['id']}).")
        ahora = _ahora()
        generada = next((a for a in self.listar(modelo, ejercicio, periodo) if a.estado == "generada"), None)
        with self.con:
            if generada:
                self.con.execute(
                    """UPDATE autoliquidaciones SET estado='presentada', casillas=?, tipo_declaracion=?, sin_actividad=?,
                       justificante=?, fecha_presentacion=?, pdf_path=?, pdf_sha256=?, origen=?, actualizada=? WHERE id=?""",
                    (self._casillas_json(casillas), tipo, sin_actividad, justificante, fecha, pdf_path, pdf_sha256,
                     origen, ahora, generada.id),
                )
                aid = generada.id
            else:
                cur = self.con.execute(
                    """INSERT INTO autoliquidaciones (modelo, ejercicio, periodo, estado, tipo_declaracion, sin_actividad,
                       casillas, justificante, fecha_presentacion, pdf_path, pdf_sha256, origen, creada, actualizada)
                       VALUES (?, ?, ?, 'presentada', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (modelo, ejercicio, periodo, tipo, sin_actividad, self._casillas_json(casillas), justificante, fecha,
                     pdf_path, pdf_sha256, origen, ahora, ahora),
                )
                aid = int(cur.lastrowid)
            self._evento(aid, "presentada", generada.to_dict()["casillas"] if generada else None,
                         {k: str(v) for k, v in casillas.items()}, f"Justificante {justificante}")
        return self.obtener(aid), generada

    def marcar_no_presentada(self, modelo: str, ejercicio: int, periodo: str, motivo: str) -> Autoliquidacion:
        if not motivo or not motivo.strip():
            raise ValueError("Indica el motivo (p. ej. 'alta en la actividad en julio').")
        if any(a.estado == "presentada" for a in self.listar(modelo, ejercicio, periodo)):
            raise ValueError("Ya hay una autoliquidación presentada para ese periodo.")
        ahora = _ahora()
        with self.con:
            cur = self.con.execute(
                """INSERT INTO autoliquidaciones (modelo, ejercicio, periodo, estado, casillas, origen, motivo, creada, actualizada)
                   VALUES (?, ?, ?, 'no_presentada', '{}', 'usuario', ?, ?, ?)""",
                (modelo, ejercicio, periodo, motivo, ahora, ahora),
            )
            aid = int(cur.lastrowid)
            self._evento(aid, "no_presentada", None, None, motivo)
        return self.obtener(aid)


__all__ = ["Autoliquidacion", "Autoliquidaciones", "Duplicada", "Libro", "Registro", "NIVELES_BLOQUEANTES", "estado_de"]
