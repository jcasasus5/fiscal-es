"""Modelos de datos: facturas, incidencias y perfil fiscal."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from .importes import CERO, parse_importe
from .periodo import Trimestre

TipoFactura = Literal["emitida", "recibida"]
Nivel = Literal["error", "fuera_alcance", "revisar", "aviso"]
# Niveles que dejan la factura pendiente y fuera de los cálculos.
NIVELES_BLOQUEANTES = ("error", "fuera_alcance", "revisar")


@dataclass
class Linea:
    base: Decimal
    tipo_iva: Decimal  # porcentaje: 21, 10, 4
    cuota: Decimal

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Linea":
        return cls(
            base=parse_importe(d["base"]),
            tipo_iva=parse_importe(d["tipo_iva"]),
            cuota=parse_importe(d["cuota"]),
        )


def _fecha(v: Any) -> date | None:
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


@dataclass
class Factura:
    tipo: TipoFactura
    numero: str
    fecha: date  # fecha de expedición
    nif_emisor: str
    nombre_emisor: str
    lineas: list[Linea]
    total: Decimal
    nif_receptor: str | None = None
    nombre_receptor: str | None = None
    retencion_irpf: Decimal = CERO
    recargo_equivalencia: Decimal = CERO
    fecha_operacion: date | None = None
    rectificativa: bool = False
    simplificada: bool = False
    bien_inversion: bool = False
    inversion_sujeto_pasivo: bool = False
    afecta_actividad: bool | None = None  # solo recibidas: ¿gasto afecto a la actividad?
    moneda: str = "EUR"
    concepto: str = ""

    @property
    def fecha_devengo(self) -> date:
        return self.fecha_operacion or self.fecha

    @property
    def trimestre(self) -> Trimestre:
        return Trimestre.de_fecha(self.fecha_devengo)

    @property
    def base_total(self) -> Decimal:
        return sum((l.base for l in self.lineas), CERO)

    @property
    def cuota_total(self) -> Decimal:
        return sum((l.cuota for l in self.lineas), CERO)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Factura":
        conocidos = {f.name for f in fields(cls)}
        desconocidos = set(d) - conocidos
        if desconocidos:
            raise ValueError(f"Campos desconocidos en la factura: {sorted(desconocidos)}")
        if d.get("tipo") not in ("emitida", "recibida"):
            raise ValueError("'tipo' debe ser 'emitida' o 'recibida'")
        for obligatorio in ("numero", "fecha", "nif_emisor", "lineas", "total"):
            if d.get(obligatorio) in (None, "", []):
                raise ValueError(f"Falta el campo obligatorio '{obligatorio}'")
        return cls(
            tipo=d["tipo"],
            numero=str(d["numero"]).strip(),
            fecha=_fecha(d["fecha"]),
            nif_emisor=str(d["nif_emisor"]).strip(),
            nombre_emisor=str(d.get("nombre_emisor") or "").strip(),
            lineas=[Linea.from_dict(l) for l in d["lineas"]],
            total=parse_importe(d["total"]),
            nif_receptor=(str(d["nif_receptor"]).strip() or None) if d.get("nif_receptor") else None,
            nombre_receptor=d.get("nombre_receptor") or None,
            retencion_irpf=parse_importe(d.get("retencion_irpf") or 0),
            recargo_equivalencia=parse_importe(d.get("recargo_equivalencia") or 0),
            fecha_operacion=_fecha(d.get("fecha_operacion")),
            rectificativa=bool(d.get("rectificativa", False)),
            simplificada=bool(d.get("simplificada", False)),
            bien_inversion=bool(d.get("bien_inversion", False)),
            inversion_sujeto_pasivo=bool(d.get("inversion_sujeto_pasivo", False)),
            afecta_actividad=d.get("afecta_actividad"),
            moneda=str(d.get("moneda") or "EUR").upper(),
            concepto=str(d.get("concepto") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


def _jsonable(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


@dataclass
class Incidencia:
    codigo: str
    nivel: Nivel
    mensaje: str

    def to_dict(self) -> dict[str, str]:
        return {"codigo": self.codigo, "nivel": self.nivel, "mensaje": self.mensaje}


@dataclass
class Perfil:
    """Situación fiscal del declarante. Se guarda en FISCAL_DATA_DIR/perfil.json.

    Todo empieza sin confirmar (None): la herramienta no supone la situación del
    usuario. Mientras falte algo, el 303 no se puede generar.
    """

    nif: str | None = None
    nombre: str | None = None  # "APELLIDOS NOMBRE", como en el censo
    regimen: str | None = None  # 'general'
    periodicidad: str | None = None  # 'trimestral'
    territorio: str | None = None  # 'comun' | 'foral'
    criterio_caja: bool | None = None
    destinatario_criterio_caja: bool | None = None
    sii: bool | None = None
    registro_devolucion_mensual: bool | None = None
    prorrata: bool | None = None
    concurso_acreedores: bool | None = None
    exonerado_390: bool | None = None  # solo se pregunta para el 4T
    forma_pago: str | None = None  # 'domiciliacion' | 'ingreso'
    iban: str | None = None
    cuotas_a_compensar: Decimal | None = None  # casilla 110: saldo de periodos anteriores
    # Solo para el modelo 390
    apellidos: str | None = None  # apellidos (persona física) o razón social
    nombre_pila: str | None = None  # nombre de pila (solo persona física)
    actividad_principal: str | None = None  # descripción breve de la actividad
    clave_actividad: str | None = None  # A01..A05, B01..B06 o C (instrucciones del 390)
    epigrafe_iae: str | None = None
    operaciones_347: bool | None = None  # ¿obligado a presentar el 347 del ejercicio?
    # Última vez que el usuario confirmó que todo lo anterior sigue vigente.
    confirmado_trimestre: str | None = None
    confirmado_fecha: str | None = None
    confirmado_fuente: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Perfil":
        conocidos = {f.name for f in fields(cls)}
        desconocidos = set(d) - conocidos
        if desconocidos:
            raise ValueError(f"Campos desconocidos en el perfil: {sorted(desconocidos)}")
        datos = dict(d)
        if datos.get("cuotas_a_compensar") not in (None, ""):
            datos["cuotas_a_compensar"] = parse_importe(datos["cuotas_a_compensar"])
        else:
            datos["cuotas_a_compensar"] = None
        return cls(**datos)

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


# Campos de la situación del declarante que hay que confirmar siempre (todos los periodos).
CAMPOS_SITUACION = (
    "regimen",
    "periodicidad",
    "territorio",
    "criterio_caja",
    "destinatario_criterio_caja",
    "sii",
    "registro_devolucion_mensual",
    "prorrata",
    "concurso_acreedores",
)

_EN_EL_303 = "Mira tu último 303 presentado (justificante PDF): "

# Campos que además pide el 390 (nombre_pila solo si el NIF es de persona física).
CAMPOS_390 = ("apellidos", "nombre_pila", "actividad_principal", "clave_actividad", "epigrafe_iae", "operaciones_347")
CLAVES_ACTIVIDAD = {
    "A01": "Arrendadores de bienes inmuebles",
    "A02": "Ganadería independiente",
    "A03": "Resto de actividades empresariales",
    "A04": "Actividades profesionales de carácter artístico o deportivo",
    "A05": "Resto de actividades profesionales",
    "B01": "Actividad agrícola",
    "B02": "Actividad ganadera dependiente",
    "B03": "Actividad forestal",
    "B04": "Producción del mejillón en batea",
    "B05": "Actividad pesquera (excepto mejillón en batea)",
    "B06": "Otras actividades no sujetas al IAE",
    "C": "Actividades no iniciadas",
}

_EN_EL_390 = "Mira tu último 390 presentado, o tu alta censal (036/037): "

# Preguntas para el usuario y dónde puede comprobarlo. El agente las usa en la entrevista.
PREGUNTAS_PERFIL: dict[str, dict[str, str]] = {
    "nif": {"pregunta": "¿Cuál es tu NIF?", "donde": _EN_EL_303 + "aparece en la cabecera."},
    "nombre": {
        "pregunta": "¿Apellidos y nombre tal como figuran en Hacienda?",
        "donde": _EN_EL_303 + "aparece junto al NIF.",
    },
    "regimen": {
        "pregunta": "¿Tributas en el régimen general del IVA? (lo normal en profesionales y la mayoría de autónomos; la alternativa es el régimen simplificado/módulos)",
        "valores": "'general' | 'simplificado'",
        "donde": _EN_EL_303 + "la casilla 'Sujeto pasivo que tributa exclusivamente en régimen simplificado' sin marcar = régimen general.",
    },
    "periodicidad": {
        "pregunta": "¿Presentas el 303 cada trimestre (1T-4T) o cada mes?",
        "valores": "'trimestral' | 'mensual'",
        "donde": _EN_EL_303 + "el campo 'Período' (1T..4T = trimestral).",
    },
    "territorio": {
        "pregunta": "¿Tu domicilio fiscal está en territorio común? (no en País Vasco ni Navarra)",
        "valores": "'comun' | 'foral'",
        "donde": "Si presentas el 303 en la Sede de la AEAT y no en una hacienda foral, es territorio común.",
    },
    "criterio_caja": {
        "pregunta": "¿Estás acogido al régimen especial del criterio de caja (pagas el IVA cuando cobras, no cuando facturas)?",
        "valores": "true | false",
        "donde": _EN_EL_303 + "casilla 'acogido al régimen especial del criterio de Caja'. También en Mis datos censales o en tu 036/037.",
    },
    "destinatario_criterio_caja": {
        "pregunta": "¿Algún proveedor te ha emitido facturas en criterio de caja (lo indican con la mención 'régimen especial del criterio de caja')?",
        "valores": "true | false",
        "donde": _EN_EL_303 + "casilla 'destinatario de operaciones acogidas al régimen especial del criterio de caja'.",
    },
    "sii": {
        "pregunta": "¿Estás en el SII (Suministro Inmediato de Información)? Los autónomos pequeños normalmente no.",
        "valores": "true | false",
        "donde": _EN_EL_303 + "casilla 'acogido voluntariamente al SII'.",
    },
    "registro_devolucion_mensual": {
        "pregunta": "¿Estás inscrito en el registro de devolución mensual (REDEME)?",
        "valores": "true | false",
        "donde": _EN_EL_303 + "casilla 'inscrito en el Registro de devolución mensual'. Si presentas trimestral, no.",
    },
    "prorrata": {
        "pregunta": "¿Haces a la vez actividades con IVA y actividades exentas (formación reglada, sanidad, seguros...) y aplicas prorrata?",
        "valores": "true | false",
        "donde": "En el 303 aparece en la página de prorratas; si nunca la has rellenado, no.",
    },
    "concurso_acreedores": {
        "pregunta": "¿Estás declarado en concurso de acreedores?",
        "valores": "true | false",
        "donde": _EN_EL_303 + "casilla 'declarado en concurso de acreedores'.",
    },
    "exonerado_390": {
        "pregunta": "¿Estás exonerado de presentar el resumen anual del IVA (modelo 390)? Solo se pregunta en el 4T.",
        "valores": "true | false",
        "donde": "Mira tu 303 del 4T anterior (casilla 'exonerado de la Declaración-resumen anual del IVA') o si presentaste un 390 en enero.",
    },
    "forma_pago": {
        "pregunta": "Si sale a ingresar, ¿quieres domiciliarlo o pagarlo tú (ingreso)?",
        "valores": "'domiciliacion' | 'ingreso'",
        "donde": _EN_EL_303 + "la sección de ingreso/domiciliación.",
    },
    "iban": {"pregunta": "¿IBAN de la cuenta para domiciliar o recibir devoluciones?", "donde": "El de tu cuenta bancaria; aparece en tu último 303 si domiciliaste."},
    "apellidos": {
        "pregunta": "¿Tus apellidos tal como figuran en Hacienda? (o la razón social si es una sociedad)",
        "donde": _EN_EL_390 + "apartado 1, Sujeto pasivo.",
    },
    "nombre_pila": {
        "pregunta": "¿Tu nombre de pila tal como figura en Hacienda?",
        "donde": _EN_EL_390 + "apartado 1, Sujeto pasivo.",
    },
    "actividad_principal": {
        "pregunta": "Describe en pocas palabras tu actividad principal (la de mayor volumen de operaciones), p. ej. 'Consultoría informática'.",
        "donde": _EN_EL_390 + "apartado 3.A.",
    },
    "clave_actividad": {
        "pregunta": "¿Qué clave corresponde a tu actividad? " + "; ".join(f"{k}: {v}" for k, v in CLAVES_ACTIVIDAD.items()),
        "valores": " | ".join(CLAVES_ACTIVIDAD),
        "donde": _EN_EL_390 + "apartado 3.B. Un profesional (servicios por cuenta propia) suele ser A05; confírmalo, no lo supongas.",
    },
    "epigrafe_iae": {
        "pregunta": "¿Cuál es el epígrafe del IAE de tu actividad principal?",
        "donde": _EN_EL_390 + "apartado 3.C. También aparece en tu alta en Hacienda (036/037) o en 'Mis datos censales'.",
    },
    "operaciones_347": {
        "pregunta": "¿Tienes que presentar el modelo 347 de este año (operaciones de más de 3.005,06 € con algún cliente o proveedor que no consten en otras declaraciones)?",
        "valores": "true | false",
        "donde": "Si presentas el 347 en febrero por ese ejercicio, la respuesta es sí. Ante la duda, consúltalo con un asesor.",
    },
    "cuotas_a_compensar": {
        "pregunta": "¿Te quedaron cuotas a compensar de trimestres anteriores (resultado negativo que no pediste devolver)?",
        "valores": "importe en euros, 0 si no",
        "donde": _EN_EL_303 + "casilla 87 (pendientes para periodos posteriores) más la casilla 72 si salió a compensar.",
    },
}


def campos_factura() -> list[str]:
    return [f.name for f in fields(Factura)]


__all__ = [
    "Factura",
    "Incidencia",
    "Linea",
    "NIVELES_BLOQUEANTES",
    "Perfil",
    "campos_factura",
    "CAMPOS_390",
    "CAMPOS_SITUACION",
    "CLAVES_ACTIVIDAD",
    "PREGUNTAS_PERFIL",
]
