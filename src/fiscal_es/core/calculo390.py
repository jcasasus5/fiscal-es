"""Cálculo determinista del modelo 390 (declaración-resumen anual del IVA).

Fuentes de cada dato (instrucciones oficiales del 390):
- Devengado y deducible por tipo, y volumen de operaciones: libro registro del ejercicio.
- [85], [95], [97]/[98]: los 303 presentados del ejercicio (registrados con su justificante).
Antes de calcular, cada trimestre del libro se cruza con su 303 presentado: si no cuadran,
el 390 no se genera (sería un resumen de algo distinto de lo que se declaró).

Alcance: el mismo que el 303 (régimen general, territorio común, trimestral, operaciones
interiores al 21/10/4 %), sin complementarias ni cuotas a compensar generadas en
periodos distintos del último (casilla [662]).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

from . import calculo303
from .importes import CERO, formato_es, redondear
from .libro import Autoliquidacion, Registro
from .modelos import CLAVES_ACTIVIDAD, Perfil
from .periodo import Trimestre

# Tipo -> (base, cuota) del IVA devengado en régimen ordinario
DEVENGADO_390 = {Decimal("4"): ("01", "02"), Decimal("10"): ("03", "04"), Decimal("21"): ("05", "06")}
# Tipo -> (base, cuota) del IVA deducible en operaciones interiores corrientes
DEDUCIBLE_390 = {Decimal("4"): ("190", "191"), Decimal("10"): ("603", "604"), Decimal("21"): ("605", "606")}

# Casillas del 303 que pueden tener importe dentro del alcance soportado.
CASILLAS_303_SOPORTADAS = {"01", "02", "03", "04", "05", "06", "07", "08", "09", "27", "28", "29", "45", "46",
                           "64", "65", "66", "69", "71", "78", "87", "110"}
# Casillas del 303 que se cruzan con el libro registro.
CASILLAS_303_CRUCE = ("01", "03", "04", "06", "07", "09", "28", "29")

DONDE_JUSTIFICANTES = (
    "En la Sede de la AEAT, 'Mi área personal' > 'Mis expedientes' (o la consulta de declaraciones "
    "presentadas del modelo 303) se pueden descargar los justificantes en PDF. Si los presentó una "
    "gestoría, pídeselos a ella."
)


@dataclass
class Resultado390:
    ejercicio: int
    casillas: dict[str, dict[str, Decimal]]
    explicacion: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    bloqueos: list[str] = field(default_factory=list)
    trimestres: list[dict[str, Any]] = field(default_factory=list)

    @property
    def generable(self) -> bool:
        return not self.bloqueos

    @property
    def resultado(self) -> Decimal:
        return self.casillas["06"]["86"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ejercicio": self.ejercicio,
            "resultado_liquidacion_anual": formato_es(self.resultado),
            "casillas": {
                pag: {c: formato_es(v) for c, v in sorted(cs.items(), key=lambda kv: int(kv[0])) if v}
                for pag, cs in self.casillas.items()
            },
            "trimestres": self.trimestres,
            "explicacion": self.explicacion,
            "avisos": self.avisos,
            "bloqueos": self.bloqueos,
            "generable": self.generable,
        }


def comprobar_perfil_390(perfil: Perfil, ejercicio: int) -> list[str]:
    p: list[str] = []
    faltan = calculo303.preguntas_pendientes(perfil, None, "390")
    if faltan:
        p.append(
            "Datos del perfil sin confirmar para el 390: " + ", ".join(faltan)
            + ". Pregúntaselos (ver_perfil(modelo='390') da las preguntas y dónde mirarlo) y guárdalos con actualizar_perfil."
        )
    # Situaciones no soportadas (mismas que el 303), sin el bloqueo de confirmación trimestral.
    for b in calculo303.comprobar_perfil(perfil, Trimestre(ejercicio, 4)):
        if b.startswith("Situación no soportada") or b.startswith("El NIF del perfil"):
            p.append(b)
    if perfil.exonerado_390:
        p.append("El perfil indica que estás exonerado del modelo 390: en ese caso no hay que presentarlo.")
    if perfil.clave_actividad and perfil.clave_actividad.upper() not in CLAVES_ACTIVIDAD:
        p.append(f"Clave de actividad no válida: {perfil.clave_actividad} (válidas: {', '.join(CLAVES_ACTIVIDAD)}).")
    confirmado = perfil.confirmado_trimestre
    if not faltan and (not confirmado or Trimestre.parse(confirmado) < Trimestre(ejercicio, 4)):
        p.append(
            f"El usuario no ha confirmado el perfil para el 4T de {ejercicio} o posterior: repásalo con él "
            f"(incluidos los datos del 390) y llama a confirmar_perfil('{ejercicio}-4T', fuente)."
        )
    return p


def _cruce(t: Trimestre, decl: Autoliquidacion, registros: list[Registro], perfil: Perfil) -> list[str]:
    """Diferencias entre el libro registro y el 303 declarado de un trimestre."""
    calc = calculo303.calcular(t, registros, perfil)
    diferencias = []
    for c in CASILLAS_303_CRUCE:
        libro = calc.casillas["01"].get(c, CERO)
        declarado = decl.casilla(c)
        if libro != declarado:
            diferencias.append(f"[{c}] libro {formato_es(libro)} / 303 {formato_es(declarado)}")
    return diferencias


def calcular(ejercicio: int, registros: Iterable[Registro], autoliqs: Iterable[Autoliquidacion],
             perfil: Perfil) -> Resultado390:
    registros = [r for r in registros if r.factura.trimestre.ejercicio == ejercicio]
    autoliqs = [a for a in autoliqs if a.modelo == "303" and a.ejercicio == ejercicio]
    bloqueos = comprobar_perfil_390(perfil, ejercicio)
    avisos: list[str] = []
    expl: list[str] = []
    trimestres: list[dict[str, Any]] = []

    pendientes = [r for r in registros if r.estado == "pendiente"]
    for r in pendientes:
        bloqueos.append(f"Factura pendiente de revisión en {r.factura.trimestre} (id {r.id}, {r.factura.numero}).")

    # --- Los cuatro 303 del ejercicio ---
    declaradas: dict[int, Autoliquidacion] = {}
    for n in range(1, 5):
        t = Trimestre(ejercicio, n)
        del_t = [a for a in autoliqs if a.periodo == t.codigo]
        presentadas = [a for a in del_t if a.estado == "presentada"]
        generadas = [a for a in del_t if a.estado == "generada"]
        no_pres = [a for a in del_t if a.estado == "no_presentada"]
        info: dict[str, Any] = {"trimestre": str(t)}
        if len(presentadas) > 1:
            bloqueos.append(f"{t}: hay {len(presentadas)} autoliquidaciones presentadas (complementaria o sustitutiva): no soportado.")
            info["estado"] = "varias_presentadas"
        elif presentadas:
            declaradas[n] = presentadas[0]
            info.update(estado="presentada", justificante=presentadas[0].justificante)
        elif n == 4 and generadas:
            declaradas[n] = generadas[0]
            info["estado"] = "generada"
            avisos.append(
                f"El 303 del {t} consta como generado pero no como presentado: preséntalo tal cual (o registra su "
                "justificante) antes de presentar el 390."
            )
        elif no_pres:
            info.update(estado="no_presentada", motivo=no_pres[0].motivo)
            if any(r.factura.trimestre == t for r in registros if r.estado != "descartada"):
                bloqueos.append(f"{t}: marcado como no presentado, pero el libro registro tiene facturas en ese trimestre.")
        else:
            info["estado"] = "falta"
            bloqueos.append(
                f"Falta el 303 del {t}. Pide al usuario el justificante y regístralo con registrar_303_presentado "
                f"(o márcalo como no presentado si no tenía actividad dada de alta). {DONDE_JUSTIFICANTES}"
            )
        if n in declaradas:
            d = declaradas[n]
            fuera = sorted(c for c, v in d.casillas.items() if v and c not in CASILLAS_303_SOPORTADAS)
            if fuera:
                bloqueos.append(f"{t}: el 303 tiene importes en casillas fuera del alcance soportado: {', '.join(fuera)}.")
            dif = _cruce(t, d, registros, perfil)
            if dif:
                bloqueos.append(
                    f"{t}: el libro registro no cuadra con el 303 declarado ({'; '.join(dif)}). Registra o corrige las "
                    "facturas de ese trimestre; si el 303 estaba mal, puede requerir una autoliquidación rectificativa."
                )
            if n < 4 and d.casilla("71") < 0:
                bloqueos.append(
                    f"{t}: el resultado fue negativo (a compensar). Las cuotas a compensar generadas en el ejercicio "
                    "(casilla 662) aún no están soportadas."
                )
            info["resultado_303"] = formato_es(d.casilla("71"))
            info["tipo_declaracion"] = d.tipo_declaracion
        trimestres.append(info)

    # --- Página 2: IVA devengado (libro registro) ---
    emitidas = [r for r in registros if r.estado == "valida" and r.factura.tipo == "emitida"]
    recibidas = [r for r in registros if r.estado == "valida" and r.factura.tipo == "recibida" and r.factura.afecta_actividad]
    p02: dict[str, Decimal] = {}
    for tipo, (cb, cc) in DEVENGADO_390.items():
        lineas = [l for r in emitidas for l in r.factura.lineas if l.tipo_iva == tipo]
        p02[cb] = redondear(sum((l.base for l in lineas), CERO))
        p02[cc] = redondear(sum((l.cuota for l in lineas), CERO))
        if lineas:
            expl.append(f"[{cb}]/[{cc}] IVA devengado al {tipo} %: base {formato_es(p02[cb])} €, cuota {formato_es(p02[cc])} €.")
    p02["33"] = p02["01"] + p02["03"] + p02["05"]
    p02["34"] = p02["02"] + p02["04"] + p02["06"]
    p02b = {"47": p02["34"]}
    expl.append(f"[33]/[34] Total bases y cuotas: {formato_es(p02['33'])} € / {formato_es(p02['34'])} €. [47] = [34].")

    # --- Páginas 3 y 4: IVA deducible (libro registro) ---
    p03: dict[str, Decimal] = {}
    for tipo, (cb, cc) in DEDUCIBLE_390.items():
        lineas = [l for r in recibidas for l in r.factura.lineas if l.tipo_iva == tipo]
        p03[cb] = redondear(sum((l.base for l in lineas), CERO))
        p03[cc] = redondear(sum((l.cuota for l in lineas), CERO))
        if lineas:
            expl.append(f"[{cb}]/[{cc}] IVA deducible al {tipo} %: base {formato_es(p03[cb])} €, cuota {formato_es(p03[cc])} €.")
    p03["48"] = p03["190"] + p03["603"] + p03["605"]
    p03["49"] = p03["191"] + p03["604"] + p03["606"]
    p04 = {"64": p03["49"]}
    p04["65"] = p02b["47"] - p04["64"]
    expl.append(f"[64] Suma de deducciones: {formato_es(p04['64'])} €. [65] Resultado régimen general = [47] − [64] = {formato_es(p04['65'])} €.")

    # --- Página 6: resultados ---
    p06: dict[str, Decimal] = {}
    p06["84"] = p04["65"]  # + [83] (simplificado) + [658]: 0 en el alcance soportado
    p06["85"] = sum((d.casilla("78") for d in declaradas.values()), CERO)
    p06["86"] = p06["84"] - p06["85"]  # + [659]: 0
    p06["95"] = sum((d.casilla("71") for d in declaradas.values() if d.casilla("71") > 0), CERO)
    ultimo = declaradas.get(4)
    if ultimo is not None and ultimo.casilla("71") < 0:
        if ultimo.tipo_declaracion == "D":
            p06["98"] = -ultimo.casilla("71")
        else:
            p06["97"] = -ultimo.casilla("71")
    p06["99"] = p02["33"]
    p06["108"] = p06["99"]
    expl.append(f"[84] Suma de resultados = [65] = {formato_es(p06['84'])} €.")
    if p06["85"]:
        expl.append(f"[85] Cuotas de ejercicios anteriores aplicadas en el año (suma de las casillas 78 de los 303): {formato_es(p06['85'])} €.")
    expl.append(f"[86] Resultado de la liquidación anual = [84] − [85] = {formato_es(p06['86'])} €.")
    expl.append(f"[95] Total ingresado en los 303 del ejercicio: {formato_es(p06['95'])} €.")
    if "97" in p06:
        expl.append(f"[97] Resultado del 4T a compensar: {formato_es(p06['97'])} €.")
    if "98" in p06:
        expl.append(f"[98] Resultado del 4T a devolver: {formato_es(p06['98'])} €.")
    expl.append(f"[99]/[108] Volumen de operaciones (bases de las facturas emitidas, sin IVA): {formato_es(p06['99'])} €.")

    # Coherencia: la suma de los resultados del régimen general de los 303 debe ser el [65] anual.
    if declaradas:
        suma46 = sum((d.casilla("46") for d in declaradas.values()), CERO)
        if suma46 != p04["65"] and not any("no cuadra" in b for b in bloqueos):
            bloqueos.append(
                f"La suma de las casillas 46 de los 303 ({formato_es(suma46)} €) no coincide con el resultado anual "
                f"[65] ({formato_es(p04['65'])} €)."
            )

    return Resultado390(
        ejercicio=ejercicio,
        casillas={"02": p02, "02B": p02b, "03": p03, "04": p04, "06": p06},
        explicacion=expl,
        avisos=avisos,
        bloqueos=bloqueos,
        trimestres=trimestres,
    )
