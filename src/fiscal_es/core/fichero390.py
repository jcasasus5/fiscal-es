"""Fichero importable del modelo 390 (declaración-resumen anual del IVA)."""

from __future__ import annotations

from . import fichero as _f
from . import nif as nifmod
from .diseno import Diseno
from .fichero import EspecModelo, texto_aeat
from .modelos import Perfil

ESPEC = EspecModelo(
    modelo="390",
    # 05 (régimen simplificado) y 08 (deducciones diferenciadas) no aplican al alcance soportado.
    paginas=("01", "02", "02B", "03", "04", "06", "07"),
    semanticos={
        "01": {
            "complementaria": r"^Indicador de p[aá]gina complementaria",
            "nif": r"Sujeto pasivo - NIF\.?\s*$",
            "apellidos": r"Sujeto pasivo - Apellidos o Raz[oó]n Social",
            "nombre": r"Sujeto pasivo - Nombre\.?$",
            "ejercicio": r"Devengo - Ejercicio",
            "redeme": r"Sujeto pasivo - Registro de devoluci[oó]n mensual",
            "grupo": r"Sujeto pasivo - Regimen especial del grupo de entidades",
            "grupo_numero": r"Sujeto pasivo - N[uú]mero de grupo",
            "grupo_dominante": r"Sujeto pasivo - dominante\?",
            "grupo_dependiente": r"Sujeto pasivo - dependiente\?",
            "grupo_163_sexies": r"163 sexies",
            "grupo_nif_dominante": r"NIF entidad dominante",
            "concurso": r"Concurso acreedores en este ejercicio",
            "criterio_caja": r"Sujeto pasivo - Regimen especial del criterio de caja",
            "destinatario_caja": r"destinatario del r[eé]gimen especial del criterio de caja",
            "gasolinas": r"gasolinas",
            "sustitutiva": r"Devengo - Sustitutiva\?",
            "sustitutiva_concurso": r"Sustitutiva por rectificaci[oó]n",
            "justificante_anterior": r"justificante declaraci[oó]n anterior",
            "actividad": r"Actividades - Principal",
            "clave_actividad": r"C[oó]digo de actividad - Principal",
            "epigrafe_iae": r"Ep[ií]grafe I\.A\.E\. - Principal",
            "operaciones_347": r"operac\. con terceras personas",
        },
        **{cod: {"complementaria": r"^Indicador de p[aá]gina complementaria"} for cod in ("02", "02B", "03", "04", "06", "07")},
    },
    conocidos={
        # Campos sin casilla que dejamos en blanco/ceros: otras actividades, declaración conjunta,
        # representante (no hay en el alcance soportado), reservados de las EEDD.
        "01": (r"- Otras", r"Declaraci[oó]n conjunta", r"^4\. Representante", r"Identificador cliente EEDD"),
        "07": (r"Actividad desarrollada",),
    },
)


def _flag(v: bool | None) -> str:
    return "1" if v else "2"


def valores_paginas(res, perfil: Perfil) -> dict[str, dict[str, object]]:
    """`res` es un Resultado390 (ver calculo390)."""
    p01: dict[str, object] = {
        "complementaria": "",
        "nif": nifmod.normalizar(perfil.nif or ""),
        "apellidos": texto_aeat(perfil.apellidos or "")[:60],
        "nombre": texto_aeat(perfil.nombre_pila or "")[:20],
        "ejercicio": str(res.ejercicio),
        "redeme": "1" if perfil.registro_devolucion_mensual else "0",
        "grupo": "0",
        "grupo_numero": "",
        "grupo_dominante": "0",
        "grupo_dependiente": "0",
        "grupo_163_sexies": "0",
        "grupo_nif_dominante": "",
        "concurso": _flag(perfil.concurso_acreedores),
        "criterio_caja": _flag(perfil.criterio_caja),
        "destinatario_caja": _flag(perfil.destinatario_criterio_caja),
        "gasolinas": "2",
        "sustitutiva": "0",
        "sustitutiva_concurso": "0",
        "justificante_anterior": "",
        "actividad": texto_aeat(perfil.actividad_principal or "")[:40],
        "clave_actividad": (perfil.clave_actividad or "").upper(),
        "epigrafe_iae": (perfil.epigrafe_iae or "").upper(),
        "operaciones_347": "1" if perfil.operaciones_347 else "0",
    }
    valores: dict[str, dict[str, object]] = {"01": p01}
    for pag, casillas in res.casillas.items():
        valores.setdefault(pag, {"complementaria": ""})
        valores[pag].update({f"[{c}]": v for c, v in casillas.items()})
    for pag in ESPEC.paginas:
        valores.setdefault(pag, {"complementaria": ""})
    return valores


def generar(diseno: Diseno, res, perfil: Perfil, version_programa: str = "0100") -> bytes:
    if not res.generable:
        raise ValueError("No se puede generar el fichero: " + " | ".join(res.bloqueos))
    return _f.generar(
        diseno, ESPEC, valores_paginas(res, perfil),
        ejercicio=res.ejercicio, periodo="0A", nif=nifmod.normalizar(perfil.nif or ""),
        version_programa=version_programa,
    )


def leer(diseno: Diseno, contenido: bytes) -> dict[str, dict[str, str]]:
    return _f.leer(diseno, ESPEC, contenido)


def nombre_fichero(res, perfil: Perfil) -> str:
    return f"{nifmod.normalizar(perfil.nif or 'SINNIF')}_390_{res.ejercicio}.390"
