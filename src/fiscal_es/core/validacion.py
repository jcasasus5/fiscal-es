"""Validación determinista de facturas y comprobación del alcance soportado."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from . import nif as nifmod
from .importes import CENT, redondear
from .modelos import Factura, Incidencia, Perfil

TIPOS_SOPORTADOS = (Decimal("21"), Decimal("10"), Decimal("4"))
TOLERANCIA_CUOTA = CENT  # por línea: diferencia admitida por redondeo
TOLERANCIA_TOTAL = Decimal("0.02")


def validar(f: Factura, perfil: Perfil | None = None, hoy: date | None = None) -> list[Incidencia]:
    inc: list[Incidencia] = []

    def add(codigo: str, nivel: str, mensaje: str) -> None:
        inc.append(Incidencia(codigo, nivel, mensaje))  # type: ignore[arg-type]

    # --- Alcance fiscal (lo no soportado queda pendiente, nunca se trata a medias) ---
    if f.rectificativa:
        add("rectificativa", "fuera_alcance", "Factura rectificativa: su tratamiento (periodo y signo) aún no está soportado.")
    if f.simplificada and f.tipo == "recibida":
        add("simplificada", "fuera_alcance", "Ticket o factura simplificada recibida: su deducibilidad aún no está soportada.")
    if f.bien_inversion:
        add("bien_inversion", "fuera_alcance", "Bien de inversión (casillas 30/31): aún no está soportado.")
    if f.inversion_sujeto_pasivo:
        add("isp", "fuera_alcance", "Operación con inversión del sujeto pasivo: fuera del alcance.")
    if f.recargo_equivalencia:
        add("recargo", "fuera_alcance", "Recargo de equivalencia: fuera del alcance.")
    if f.moneda != "EUR":
        add("moneda", "fuera_alcance", f"Factura en {f.moneda}: solo se admiten facturas en euros.")
    for l in f.lineas:
        if l.tipo_iva not in TIPOS_SOPORTADOS:
            add(
                "tipo_iva",
                "fuera_alcance",
                f"Tipo de IVA {l.tipo_iva} %: solo se soportan 21, 10 y 4 % (exentas, no sujetas o 0 % quedan fuera).",
            )
        if l.base < 0 or l.cuota < 0:
            add("negativo", "fuera_alcance", "Importes negativos: parece una rectificativa o un abono, aún no soportado.")

    # --- Identificación ---
    if nifmod.parece_extranjero(f.nif_emisor):
        add("emisor_extranjero", "fuera_alcance", f"Emisor con NIF extranjero ({f.nif_emisor}): operación intracomunitaria o importación, fuera del alcance.")
    elif not nifmod.es_valido(f.nif_emisor):
        add("nif_emisor", "error", f"El NIF del emisor '{f.nif_emisor}' no es válido (dígito de control).")

    if f.nif_receptor:
        if nifmod.parece_extranjero(f.nif_receptor):
            add("receptor_extranjero", "fuera_alcance", f"Receptor con NIF extranjero ({f.nif_receptor}): entrega intracomunitaria o exportación, fuera del alcance.")
        elif not nifmod.es_valido(f.nif_receptor):
            add("nif_receptor", "error", f"El NIF del receptor '{f.nif_receptor}' no es válido (dígito de control).")

    if perfil and perfil.nif:
        propio = nifmod.normalizar(perfil.nif)
        if f.tipo == "emitida" and nifmod.normalizar(f.nif_emisor) != propio:
            add("no_eres_emisor", "error", "Factura marcada como emitida pero el emisor no es tu NIF. ¿Es una factura recibida?")
        if f.tipo == "recibida":
            if nifmod.normalizar(f.nif_emisor) == propio:
                add("eres_emisor", "error", "Factura marcada como recibida pero el emisor eres tú. ¿Es una factura emitida?")
            elif not f.nif_receptor or nifmod.normalizar(f.nif_receptor) != propio:
                add("receptor_no_eres_tu", "revisar", "La factura recibida no está a tu NIF: sin él, el IVA no es deducible.")

    if f.tipo == "emitida" and not f.nif_receptor:
        add("sin_receptor", "aviso", "La factura emitida no indica NIF del destinatario.")
    if f.tipo == "recibida" and f.afecta_actividad is None:
        add("afectacion", "revisar", "Confirma que el gasto está afecto a tu actividad (afecta_actividad=true) para poder deducir su IVA.")
    if f.tipo == "recibida" and f.afecta_actividad is False:
        add("no_afecta", "aviso", "Gasto no afecto a la actividad: se registra pero su IVA no se deduce.")

    # --- Aritmética ---
    if not f.lineas:
        add("sin_lineas", "error", "La factura no tiene líneas de base/tipo/cuota.")
    for i, l in enumerate(f.lineas, 1):
        esperada = redondear(l.base * l.tipo_iva / 100)
        if abs(esperada - l.cuota) > TOLERANCIA_CUOTA:
            add(
                "cuota",
                "error",
                f"Línea {i}: base {l.base} × {l.tipo_iva} % = {esperada}, pero la cuota indicada es {l.cuota}.",
            )
    esperado = f.base_total + f.cuota_total + f.recargo_equivalencia - f.retencion_irpf
    if abs(esperado - f.total) > TOLERANCIA_TOTAL:
        add(
            "total",
            "error",
            f"El total no cuadra: base {f.base_total} + IVA {f.cuota_total} − retención {f.retencion_irpf}"
            f" = {redondear(esperado)}, pero el total indicado es {f.total}.",
        )
    if f.retencion_irpf < 0:
        add("retencion", "error", "La retención de IRPF debe indicarse en positivo.")

    # --- Fechas ---
    hoy = hoy or date.today()
    if f.fecha > hoy:
        add("fecha_futura", "revisar", f"La fecha {f.fecha} es posterior a hoy.")
    if f.fecha_operacion and f.fecha_operacion > f.fecha and f.fecha_operacion.year != f.fecha.year:
        add("fecha_operacion", "aviso", "La fecha de operación es de otro ejercicio que la de expedición.")

    return inc
