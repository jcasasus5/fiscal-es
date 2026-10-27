"""Cálculo determinista de las casillas del modelo 303.

Alcance: régimen general, operaciones interiores, tipos 21/10/4 %, IVA soportado
en operaciones interiores corrientes, territorio común, periodicidad trimestral.
Cualquier situación fuera de este alcance bloquea la generación con un motivo claro.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Literal

from . import iban as ibanmod
from . import nif as nifmod
from .importes import CERO, formato_es, redondear
from .libro import Registro
from .modelos import CAMPOS_390, CAMPOS_SITUACION, Perfil
from .periodo import Trimestre

# Tipo de IVA -> (casilla base, casilla cuota) en el IVA devengado del régimen general.
CASILLAS_DEVENGADO = {
    Decimal("4"): ("01", "03"),
    Decimal("10"): ("04", "06"),
    Decimal("21"): ("07", "09"),
}

OpcionNegativo = Literal["compensar", "devolver"]


@dataclass
class Resultado303:
    trimestre: Trimestre
    casillas: dict[str, dict[str, Decimal]]  # página -> casilla -> importe
    identificacion: dict[str, str]  # valores de la página 01 que no son casillas
    tipo_declaracion: str  # I, U, N, C, D
    sin_actividad: bool
    explicacion: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    bloqueos: list[str] = field(default_factory=list)
    facturas_incluidas: list[int] = field(default_factory=list)

    @property
    def resultado(self) -> Decimal:
        return self.casillas["03"]["71"]

    @property
    def generable(self) -> bool:
        return not self.bloqueos

    def to_dict(self) -> dict[str, Any]:
        return {
            "trimestre": str(self.trimestre),
            "resultado": formato_es(self.resultado),
            "tipo_declaracion": self.tipo_declaracion,
            "tipo_declaracion_texto": TEXTO_TIPO.get(self.tipo_declaracion, self.tipo_declaracion),
            "sin_actividad": self.sin_actividad,
            "casillas": {
                pag: {cas: formato_es(v) for cas, v in sorted(cs.items(), key=lambda kv: int(kv[0])) if v}
                for pag, cs in self.casillas.items()
            },
            "explicacion": self.explicacion,
            "avisos": self.avisos,
            "bloqueos": self.bloqueos,
            "generable": self.generable,
            "facturas_incluidas": self.facturas_incluidas,
        }


TEXTO_TIPO = {
    "I": "Ingreso",
    "U": "Ingreso por domiciliación bancaria",
    "N": "Sin actividad / resultado cero",
    "C": "A compensar en periodos posteriores",
    "D": "A devolver por transferencia",
}


def preguntas_pendientes(perfil: Perfil, t: Trimestre | None, modelo: str = "303") -> list[str]:
    """Campos del perfil que aún no se le han preguntado al usuario (siguen a None).

    La forma de pago y el IBAN no están aquí: solo hacen falta según el resultado.
    Para el 390 se piden además los datos de la página 1 (apellidos, actividad…).
    """
    campos = ["nif", "nombre", *CAMPOS_SITUACION]
    if modelo == "303":
        campos.append("cuotas_a_compensar")
        if t is not None and t.es_ultimo:
            campos.append("exonerado_390")
    else:
        campos.append("exonerado_390")
        for c in CAMPOS_390:
            if c == "nombre_pila" and perfil.nif and nifmod.tipo(perfil.nif) == "CIF":
                continue  # las sociedades no tienen nombre de pila
            campos.append(c)
    return [c for c in campos if getattr(perfil, c) in (None, "")]


def comprobar_perfil(perfil: Perfil, t: Trimestre) -> list[str]:
    """Bloqueos del perfil: datos sin confirmar, datos no válidos o situaciones no soportadas."""
    p: list[str] = []
    faltan = preguntas_pendientes(perfil, t)
    if faltan:
        p.append(
            "Datos del perfil sin confirmar con el usuario: " + ", ".join(faltan)
            + ". Pregúntaselos (ver_perfil da las preguntas y dónde mirarlo) y guárdalos con actualizar_perfil."
        )
    if perfil.nif and not nifmod.es_valido(perfil.nif):
        p.append(f"El NIF del perfil ({perfil.nif}) no es válido.")
    no_soportado = []
    if perfil.regimen not in (None, "general"):
        no_soportado.append(f"régimen '{perfil.regimen}'")
    if perfil.periodicidad not in (None, "trimestral"):
        no_soportado.append(f"periodicidad '{perfil.periodicidad}'")
    if perfil.territorio not in (None, "comun"):
        no_soportado.append("tributación foral")
    for campo, texto in (
        ("criterio_caja", "régimen especial del criterio de caja"),
        ("sii", "SII"),
        ("registro_devolucion_mensual", "REDEME"),
        ("prorrata", "prorrata"),
        ("concurso_acreedores", "concurso de acreedores"),
    ):
        if getattr(perfil, campo):
            no_soportado.append(texto)
    if no_soportado:
        p.append("Situación no soportada por la herramienta: " + ", ".join(no_soportado) + ".")
    if t.es_ultimo and perfil.exonerado_390:
        p.append("Exonerado del 390: en el 4T hay que rellenar la página 4 (resumen anual), que aún no está soportada.")
    if not faltan and perfil.confirmado_trimestre != str(t):
        previo = f" (última confirmación: {perfil.confirmado_trimestre})" if perfil.confirmado_trimestre else ""
        p.append(
            f"El usuario no ha confirmado que su perfil sigue vigente para {t}{previo}: repásalo con él, "
            "incluidas las cuotas a compensar de periodos anteriores, y llama a confirmar_perfil."
        )
    return p


def _flags(perfil: Perfil, t: Trimestre) -> dict[str, str]:
    """Casillas de identificación (página 01) según las notas del diseño de registro."""
    ultimo = t.es_ultimo
    return {
        "foral": "2",
        "redeme": "2",
        "simplificado": "3",  # NO (solo régimen general)
        "conjunta": "2",
        "criterio_caja": "2",
        "destinatario_caja": "1" if perfil.destinatario_criterio_caja else "2",
        # Nota 6: "2" equivale a casilla en blanco fuera del último periodo y a NO en el 4T.
        "prorrata_opcion": "2",
        "prorrata_revocacion": "2",
        "concurso": "2",
        "concurso_fecha": "",
        "concurso_tipo": "",
        "sii": "2",
        "exonerado_390": ("1" if perfil.exonerado_390 else "2") if ultimo else "0",
        # Nota 3: '0' salvo en el último periodo para los exonerados del 390.
        "volumen_distinto_cero": "0",
        "gasolinas": "0",
    }


def calcular(
    t: Trimestre,
    registros: Iterable[Registro],
    perfil: Perfil,
    opcion_negativo: OpcionNegativo | None = None,
) -> Resultado303:
    registros = [r for r in registros if r.factura.trimestre == t]
    validas = [r for r in registros if r.estado == "valida"]
    pendientes = [r for r in registros if r.estado == "pendiente"]
    emitidas = [r for r in validas if r.factura.tipo == "emitida"]
    recibidas = [r for r in validas if r.factura.tipo == "recibida" and r.factura.afecta_actividad]
    no_deducibles = [r for r in validas if r.factura.tipo == "recibida" and not r.factura.afecta_actividad]

    p1: dict[str, Decimal] = {}
    expl: list[str] = []
    avisos: list[str] = []
    bloqueos: list[str] = list(comprobar_perfil(perfil, t))

    for r in pendientes:
        motivos = "; ".join(i.mensaje for i in r.incidencias if i.nivel != "aviso")
        bloqueos.append(f"Factura pendiente de revisión (id {r.id}, {r.factura.numero}): {motivos}")

    # IVA devengado por tipo
    for tipo, (cas_base, cas_cuota) in CASILLAS_DEVENGADO.items():
        base = cuota = CERO
        usadas = []
        for r in emitidas:
            lineas = [l for l in r.factura.lineas if l.tipo_iva == tipo]
            if lineas:
                base += sum((l.base for l in lineas), CERO)
                cuota += sum((l.cuota for l in lineas), CERO)
                usadas.append(r.factura.numero)
        p1[cas_base], p1[cas_cuota] = redondear(base), redondear(cuota)
        if usadas:
            expl.append(
                f"[{cas_base}]/[{cas_cuota}] IVA devengado al {tipo} %: base {formato_es(base)} €, "
                f"cuota {formato_es(cuota)} € (facturas emitidas: {', '.join(usadas)})."
            )
    p1["27"] = p1["03"] + p1["06"] + p1["09"]
    expl.append(f"[27] Total cuota devengada = [03] + [06] + [09] = {formato_es(p1['27'])} €.")

    # IVA deducible: operaciones interiores corrientes
    p1["28"] = redondear(sum((r.factura.base_total for r in recibidas), CERO))
    p1["29"] = redondear(sum((r.factura.cuota_total for r in recibidas), CERO))
    if recibidas:
        expl.append(
            f"[28]/[29] IVA deducible en operaciones interiores corrientes: base {formato_es(p1['28'])} €, "
            f"cuota {formato_es(p1['29'])} € (facturas recibidas: {', '.join(r.factura.numero for r in recibidas)})."
        )
    if no_deducibles:
        avisos.append(
            "Facturas recibidas no afectas a la actividad (no se deducen): "
            + ", ".join(r.factura.numero for r in no_deducibles)
        )
    p1["45"] = p1["29"]
    p1["46"] = p1["27"] - p1["45"]
    expl.append(f"[45] Total a deducir = {formato_es(p1['45'])} €. [46] Resultado régimen general = [27] − [45] = {formato_es(p1['46'])} €.")

    # Resultado (página 03)
    p3: dict[str, Decimal] = {}
    p3["64"] = p1["46"]
    p3["65"] = Decimal("100")  # territorio común: 100 % atribuible al Estado
    p3["66"] = redondear(p3["64"] * p3["65"] / 100)
    p3["110"] = redondear(perfil.cuotas_a_compensar or CERO)
    p3["78"] = min(p3["110"], max(CERO, p3["66"]))
    p3["87"] = p3["110"] - p3["78"]
    p3["69"] = p3["66"] - p3["78"]
    p3["71"] = p3["69"]
    if p3["110"]:
        expl.append(
            f"[110] Cuotas a compensar de periodos anteriores: {formato_es(p3['110'])} €; "
            f"[78] aplicadas en este periodo: {formato_es(p3['78'])} €; [87] quedan para periodos posteriores: {formato_es(p3['87'])} €."
        )
    expl.append(f"[64]=[66] Suma de resultados: {formato_es(p3['66'])} € (100 % atribuible a la Administración del Estado).")

    sin_actividad = not emitidas and not recibidas
    resultado = p3["71"]
    if resultado > 0:
        if perfil.forma_pago == "domiciliacion":
            tipo_decl = "U"
        elif perfil.forma_pago == "ingreso":
            tipo_decl = "I"
        else:
            tipo_decl = "I"
            bloqueos.append("Sale a ingresar: indica la forma de pago en el perfil (forma_pago: 'domiciliacion' o 'ingreso').")
    elif resultado == 0:
        tipo_decl = "N"
    elif not t.es_ultimo:
        tipo_decl = "C"
    elif opcion_negativo == "devolver":
        tipo_decl = "D"
    elif opcion_negativo == "compensar":
        tipo_decl = "C"
    else:
        tipo_decl = "C"
        bloqueos.append("En el 4T el resultado negativo se puede compensar o devolver: indica opcion_negativo.")

    if tipo_decl in ("U", "D"):
        if not perfil.iban:
            bloqueos.append("Falta el IBAN en el perfil para domiciliar o recibir la devolución.")
        elif not ibanmod.es_valido(perfil.iban):
            bloqueos.append(f"El IBAN del perfil no es válido: {perfil.iban}")
        elif tipo_decl == "U" and not ibanmod.normalizar(perfil.iban).startswith("ES"):
            bloqueos.append("La domiciliación del 303 requiere una cuenta española (IBAN ES).")

    if sin_actividad:
        expl.append("No hay facturas válidas en el trimestre: se declara SIN ACTIVIDAD con resultado 0.")
    if resultado > 0:
        expl.append(f"[71] Resultado: {formato_es(resultado)} € a ingresar ({TEXTO_TIPO[tipo_decl].lower()}).")
    elif resultado < 0:
        expl.append(f"[71] Resultado: {formato_es(resultado)} € ({TEXTO_TIPO[tipo_decl].lower()}).")
    else:
        expl.append("[71] Resultado: 0,00 €.")

    return Resultado303(
        trimestre=t,
        casillas={"01": p1, "03": p3},
        identificacion=_flags(perfil, t),
        tipo_declaracion=tipo_decl,
        sin_actividad=sin_actividad,
        explicacion=expl,
        avisos=avisos,
        bloqueos=bloqueos,
        facturas_incluidas=[r.id for r in emitidas + recibidas],
    )
