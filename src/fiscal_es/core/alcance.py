"""Qué sabe hacer la herramienta y qué no. Fuente única para la tool `capacidades`,
la skill y el README: si cambia el alcance, se cambia aquí."""

from __future__ import annotations

from typing import Any

from .calculo303 import CASILLAS_DEVENGADO
from .validacion import TIPOS_SOPORTADOS

# Casillas que calcula la herramienta (el resto va a cero o con su constante del diseño).
CASILLAS_CALCULADAS: dict[str, dict[str, str]] = {
    "01": {
        **{c: f"Base imponible al {t} %" for t, (c, _) in CASILLAS_DEVENGADO.items()},
        **{c: f"Cuota devengada al {t} %" for t, (_, c) in CASILLAS_DEVENGADO.items()},
        "27": "Total cuota devengada",
        "28": "Base de IVA soportado en operaciones interiores corrientes",
        "29": "Cuota de IVA soportado deducible en operaciones interiores corrientes",
        "45": "Total a deducir",
        "46": "Resultado régimen general",
    },
    "03": {
        "64": "Suma de resultados",
        "65": "% atribuible a la Administración del Estado (100 % en territorio común)",
        "66": "Atribuible a la Administración del Estado",
        "110": "Cuotas a compensar pendientes de periodos anteriores (dato del perfil)",
        "78": "Cuotas a compensar aplicadas en este periodo",
        "87": "Cuotas a compensar pendientes para periodos posteriores",
        "69": "Resultado de la autoliquidación",
        "71": "Resultado",
    },
}

SOPORTADO = [
    "Autónomos y sociedades en régimen general del IVA, con periodicidad trimestral y en territorio común.",
    "Facturas emitidas a clientes en España al " + ", ".join(f"{t} %" for t in TIPOS_SOPORTADOS) + ", con o sin retención de IRPF.",
    "IVA soportado deducible de gastos de la actividad (afectos al 100 %) con factura completa a tu NIF de proveedores españoles: casillas 28/29.",
    "Cuotas a compensar de periodos anteriores (casillas 110, 78 y 87).",
    "Resultado a ingresar (ingreso o domiciliación), a compensar, a devolver (solo en el 4T), cero o sin actividad.",
    "Fichero .303 para importar en la Sede según el diseño de registro oficial del ejercicio, con comprobación de diseños nuevos.",
    "Modelo 390 (resumen anual) del mismo alcance: a partir del libro registro y de los 303 presentados del año, que se registran con su justificante; fichero .390 para importar en la Sede.",
    "Registro de los 303 presentados (generados aquí o hechos a mano antes), cruzados con el libro registro.",
]

NO_SOPORTADO = [
    ("regimenes", "Régimen simplificado (módulos), recargo de equivalencia, criterio de caja, prorrata, SII, REDEME, tributación foral, periodicidad mensual."),
    ("extranjero", "Clientes o proveedores extranjeros: entregas y adquisiciones intracomunitarias, exportaciones e importaciones, inversión del sujeto pasivo (p. ej. Google, Meta, AWS o Adobe facturando desde Irlanda)."),
    ("exentas", "Operaciones exentas o no sujetas (formación reglada, sanidad, seguros…) y tipos distintos de 21/10/4 %."),
    ("rectificativas", "Facturas rectificativas y abonos; autoliquidaciones rectificativas o complementarias."),
    ("tickets", "Tickets o facturas simplificadas como gasto deducible."),
    ("mixtos", "Gastos de uso mixto que solo se deducen en parte (vehículo, suministros de la vivienda…)."),
    ("inversion", "Bienes de inversión (casillas 30/31) y regularizaciones."),
    ("390_exonerados", "Página 4 del 303 del 4T para exonerados del modelo 390."),
    ("390", "En el 390: autoliquidaciones complementarias o declaraciones sustitutivas, cuotas a compensar generadas en periodos distintos del último (casilla 662), varias actividades, prorrata y regímenes especiales."),
    ("irpf", "Gastos deducibles en IRPF (modelo 130 o la renta): son otra declaración."),
]

COMPORTAMIENTO = [
    "Lo no soportado no se trata a medias: la factura queda pendiente con un aviso y el 303 no se genera hasta resolverlo o descartarla.",
    "Ningún importe lo calcula el LLM: todas las casillas salen de calcular_303 / generar_303.",
    "El perfil fiscal empieza sin confirmar y hay que confirmarlo cada trimestre.",
    "La herramienta nunca presenta nada ante la AEAT ni maneja certificados.",
]


def capacidades() -> dict[str, Any]:
    return {
        "soportado": SOPORTADO,
        "no_soportado": [{"tema": k, "detalle": v} for k, v in NO_SOPORTADO],
        "casillas_calculadas": CASILLAS_CALCULADAS,
        "casillas_calculadas_390": CASILLAS_CALCULADAS_390,
        "comportamiento": COMPORTAMIENTO,
        "dudas": "Para dudas sobre cómo se rellena una casilla o qué significa, usa consultar_instrucciones_303 / "
                 "consultar_instrucciones_390 (instrucciones oficiales del ejercicio) e info_casilla. Si la respuesta no "
                 "está ahí, dilo y no la inventes.",
    }


# Casillas del 390 que calcula la herramienta.
CASILLAS_CALCULADAS_390: dict[str, dict[str, str]] = {
    "02": {"01": "Base al 4 %", "02": "Cuota al 4 %", "03": "Base al 10 %", "04": "Cuota al 10 %",
           "05": "Base al 21 %", "06": "Cuota al 21 %", "33": "Total bases", "34": "Total cuotas"},
    "02B": {"47": "Total cuotas IVA y recargo de equivalencia"},
    "03": {"190": "Base deducible al 4 %", "191": "Cuota deducible al 4 %", "603": "Base deducible al 10 %",
           "604": "Cuota deducible al 10 %", "605": "Base deducible al 21 %", "606": "Cuota deducible al 21 %",
           "48": "Total bases deducibles corrientes", "49": "Total cuotas deducibles corrientes"},
    "04": {"64": "Suma de deducciones", "65": "Resultado régimen general"},
    "06": {"84": "Suma de resultados", "85": "Compensación de cuotas del ejercicio anterior",
           "86": "Resultado de la liquidación", "95": "Total resultados a ingresar de los 303",
           "97": "Resultado del último periodo a compensar", "98": "Resultado del último periodo a devolver",
           "99": "Volumen de operaciones en régimen general", "108": "Total volumen de operaciones"},
}


def calculada(pagina: str, casilla: str, modelo: str = "303") -> str | None:
    tabla = CASILLAS_CALCULADAS_390 if modelo == "390" else CASILLAS_CALCULADAS
    return tabla.get(pagina, {}).get(casilla)
