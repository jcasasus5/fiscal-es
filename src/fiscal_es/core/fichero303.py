"""Fichero importable del modelo 303: qué valor lleva cada campo del diseño oficial."""

from __future__ import annotations

from . import iban as ibanmod
from . import nif as nifmod
from .calculo303 import Resultado303
from .diseno import Diseno
from .fichero import ENCODING, EspecModelo, ErrorDiseno, asignar, campo, formatear, texto_aeat
from . import fichero as _f
from .modelos import Perfil

ESPEC = EspecModelo(
    modelo="303",
    paginas=("01", "03", "DID"),
    semanticos={
        "01": {
            "complementaria": r"^Indicador de p[aá]gina complementaria",
            "tipo_declaracion": r"^Tipo Declaraci[oó]n",
            "nif": r"Identificaci[oó]n \(1\) - NIF$",
            "nombre": r"Apellidos y nombre o Raz[oó]n social",
            "ejercicio": r"Devengo \(2\) - Ejercicio",
            "periodo": r"Devengo \(2\) - Per[ií]odo",
            "foral": r"Tributaci[oó]n exclusivamente foral",
            "redeme": r"Registro de devoluci[oó]n mensual",
            "simplificado": r"exclusivamente en r[eé]gimen simplificado",
            "conjunta": r"Autoliquidaci[oó]n conjunta",
            "criterio_caja": r"acogido al r[eé]gimen especial del criterio de Caja",
            "destinatario_caja": r"destinatario de operaciones acogidas al r[eé]gimen especial del criterio de caja",
            "prorrata_opcion": r"\(1\) - Opci[oó]n por la aplicaci[oó]n de la prorrata especial",
            "prorrata_revocacion": r"Revocaci[oó]n de la opci[oó]n",
            "concurso": r"declarado en concurso de acreedores",
            "concurso_fecha": r"Fecha en que se dict[oó] el auto",
            "concurso_tipo": r"Tipo de autoliquidaci[oó]n si se ha dictado auto",
            "sii": r"voluntariamente al SII",
            "exonerado_390": r"exonerado de la Declaraci[oó]n-resumen anual",
            "volumen_distinto_cero": r"volumen anual de operaciones distinto de cero",
            "gasolinas": r"derecho a deducir pago a cuenta de entregas de gasolinas",
        },
        "03": {
            "sin_actividad": r"Declaraci[oó]n Sin actividad",
            "rectificativa": r"Rectificativa - Autoliquidaci[oó]n rectificativa$",
            "rect_justificante": r"N[uú]mero justificante identificativo",
            "rect_baja_domiciliacion": r"dar de baja/modificar la domiciliaci[oó]n",
            "rect_motivo": r"Motivo de la rectificaci[oó]n: Rectificaciones",
            "rect_motivo_discrepancia": r"Motivo de la rectificaci[oó]n: Discrepancia",
        },
        "DID": {
            "swift": r"SWIFT-BIC",
            "iban": r"IBAN",
            "banco": r"Banco/Bank name",
            "banco_direccion": r"Direcci[oó]n del Banco",
            "banco_ciudad": r"Ciudad/City",
            "banco_pais": r"C[oó]digo Pa[ií]s",
            "marca_sepa": r"Marca SEPA",
        },
    },
)

# Compatibilidad con el nombre anterior.
_texto_aeat = texto_aeat

__all__ = ["ENCODING", "ESPEC", "ErrorDiseno", "asignar", "campo", "formatear", "generar", "leer",
           "nombre_fichero", "valores_paginas"]


def valores_paginas(res: Resultado303, perfil: Perfil) -> dict[str, dict[str, object]]:
    t = res.trimestre
    p01: dict[str, object] = {
        "tipo_declaracion": res.tipo_declaracion,
        "nif": nifmod.normalizar(perfil.nif or ""),
        "nombre": texto_aeat(perfil.nombre or "")[:80].rstrip(),
        "ejercicio": str(t.ejercicio),
        "periodo": t.codigo,
        "complementaria": "",
        **res.identificacion,
    }
    for cas, v in res.casillas["01"].items():
        p01[f"[{cas}]"] = v
    p03: dict[str, object] = {f"[{cas}]": v for cas, v in res.casillas["03"].items()}
    p03.update(
        {
            "sin_actividad": "X" if res.sin_actividad else "",
            "rectificativa": "",
            "rect_justificante": "",
            "rect_baja_domiciliacion": "",
            "rect_motivo": "",
            "rect_motivo_discrepancia": "",
        }
    )
    iban = ibanmod.normalizar(perfil.iban or "") if res.tipo_declaracion in ("U", "D") else ""
    did: dict[str, object] = {
        "swift": "",
        "iban": iban,
        "banco": "",
        "banco_direccion": "",
        "banco_ciudad": "",
        "banco_pais": "",
        "marca_sepa": ("1" if iban.startswith("ES") else "2") if res.tipo_declaracion == "D" and iban else "0",
    }
    return {"01": p01, "03": p03, "DID": did}


def generar(diseno: Diseno, res: Resultado303, perfil: Perfil, version_programa: str = "0100") -> bytes:
    """Contenido del fichero (ISO-8859-1, una sola línea, sin salto final)."""
    if not res.generable:
        raise ValueError("No se puede generar el fichero: " + " | ".join(res.bloqueos))
    return _f.generar(
        diseno, ESPEC, valores_paginas(res, perfil),
        ejercicio=res.trimestre.ejercicio, periodo=res.trimestre.codigo,
        nif=nifmod.normalizar(perfil.nif or ""), version_programa=version_programa,
    )


def leer(diseno: Diseno, contenido: bytes) -> dict[str, dict[str, str]]:
    return _f.leer(diseno, ESPEC, contenido)


def nombre_fichero(res: Resultado303, perfil: Perfil) -> str:
    return f"{nifmod.normalizar(perfil.nif or 'SINNIF')}_303_{res.trimestre.ejercicio}_{res.trimestre.codigo}.303"
