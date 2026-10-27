"""Servidor MCP (stdio). Capa fina sobre `Servicio`: aquí no hay lógica fiscal."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Annotated, Any, Iterator, Literal

from fastmcp import FastMCP
from pydantic import Field

from . import __version__
from .servicio import Servicio

INSTRUCCIONES = """\
Eres el gestor del IVA trimestral (modelo 303) de un autónomo en España. Estas tools
hacen todo lo determinista: validan facturas, llevan el libro registro, calculan las
casillas y generan el fichero oficial. Tú localizas las facturas con tus propias
herramientas (carpetas, email), le haces al usuario las preguntas necesarias y le
explicas el resultado.

Reglas:
- NUNCA calcules importes ni casillas tú mismo: usa calcular_303 / generar_303.
- NUNCA inventes cómo se rellena una casilla ni qué significa: consúltalo en las
  instrucciones oficiales del ejercicio (consultar_instrucciones_303) o en el diseño
  (info_casilla) y cita la fuente. Si no aparece, dilo.
- Si algo no está en el alcance de la herramienta (capacidades), díselo al usuario
  tal cual en vez de forzarlo.
- NUNCA presentes nada ante la AEAT ni pidas certificados o contraseñas. El usuario
  importa el fichero, revisa, firma y envía en la Sede.
- Ante una duda fiscal, pregunta al usuario en lugar de asumir.
- No des por buena una factura que no cuadra: corrígela con corregir_factura o
  pregunta. Solo usa confirmar_factura cuando el usuario lo haya validado.

Flujo para "hazme el 303 del <trimestre>":
0. Si no lo has hecho en esta conversación, capacidades() para saber qué está soportado.
1. plazos() para situar el trimestre y la fecha límite.
2. comprobar_diseno_303(trimestre). Si hay diseño nuevo y es compatible,
   instalar_diseno_303(trimestre). Si no es compatible, para y explícaselo al usuario.
3. ver_perfil(trimestre). La herramienta no supone nada sobre la situación del
   usuario: todo empieza sin confirmar.
   - Si hay preguntas_pendientes: lo mejor es leer su último 303 presentado
     (justificante PDF), donde están las casillas de identificación que aceptó la
     AEAT (sin marcar = NO), el NIF, el nombre, la forma de pago y las cuotas a
     compensar. Lo que no salga de ahí, pregúntaselo con la pregunta de cada campo.
     Guarda solo lo que él confirme, con actualizar_perfil.
   - Después, en CADA trimestre: repasa con él el perfil (sobre todo forma de pago,
     IBAN y cuotas a compensar de periodos anteriores) y llama a
     confirmar_perfil(trimestre, fuente). Sin eso no se genera el 303.
4. Pregunta dónde están las facturas del trimestre (emitidas y recibidas), búscalas,
   lee cada una y llama a registrar_factura con sus datos y la ruta del PDF.
5. Resuelve con el usuario las facturas pendientes (listar_facturas estado=pendiente).
6. calcular_303(trimestre) y explica el resultado casilla a casilla.
7. generar_303(trimestre) y dale la ruta del fichero y los pasos para la Sede.
8. Cuando lo haya presentado, pídele el justificante PDF, léelo y guárdalo con
   registrar_303_presentado: así queda registrado junto a los generados y sirve para el 390.

Flujo para el 390 (resumen anual, enero, junto al 303 del 4T; no lo presentan los exonerados):
1. comprobar_diseno_390(ejercicio) e instalar_diseno_390 si hay uno nuevo y compatible.
2. ver_perfil(ejercicio, modelo='390'): pregunta lo que falte (apellidos y nombre por
   separado, actividad, clave, epígrafe IAE, 347) y confirma el perfil para el 4T.
3. listar_autoliquidaciones(ejercicio): para cada 303 del año que no esté registrado
   (p. ej. presentados a mano antes de usar esta herramienta), pide al usuario el
   justificante (si no lo tiene, explícale de dónde descargarlo), léelo y regístralo
   con registrar_303_presentado. Si en un trimestre no tenía actividad dada de alta,
   marcar_303_no_presentado.
4. calcular_390(ejercicio): cruza el libro registro con los 303 presentados; explica el
   resultado y resuelve los bloqueos con el usuario.
5. generar_390(ejercicio) y dale la ruta y los pasos para importarlo en la Sede.
Dudas sobre el 390: consultar_instrucciones_390 (si las del ejercicio aún no están
publicadas, usa las del anterior y avisa de ello).
"""

mcp = FastMCP("fiscal-es", instructions=INSTRUCCIONES, version=__version__)
_svc: Servicio | None = None
_lock = threading.Lock()


@contextmanager
def _servicio() -> Iterator[Servicio]:
    """Las tools síncronas se ejecutan en hilos: una sola a la vez sobre el libro."""
    global _svc
    with _lock:
        if _svc is None:
            _svc = Servicio()
        yield _svc


Trimestre = Annotated[str, Field(description="Trimestre en formato 'AAAA-NT', p. ej. '2027-1T'.")]
Motivo = Annotated[str, Field(description="Por qué se hace el cambio. Queda registrado en el historial.")]


@mcp.tool
def capacidades() -> dict[str, Any]:
    """Qué sabe hacer la herramienta y qué no (regímenes, operaciones, deducciones),
    qué casillas calcula y cómo se comporta con lo no soportado. Consúltala al empezar
    y cuando el usuario pregunte si puede usarla para su caso."""
    with _servicio() as s:
        return s.capacidades()


@mcp.tool
def consultar_instrucciones_303(
    trimestre: Trimestre,
    consulta: Annotated[str | None, Field(description=(
        "Qué buscar: número de casilla ('casilla 28'), concepto ('sin actividad', 'cuotas a compensar', "
        "'exonerados 390'...). Vacío = índice de secciones de las instrucciones del ejercicio."
    ))] = None,
    max_resultados: Annotated[int, Field(ge=1, le=15)] = 6,
) -> dict[str, Any]:
    """Busca en las INSTRUCCIONES OFICIALES del modelo 303 publicadas por la AEAT para el
    ejercicio del trimestre (ficha G414 de la Sede) y devuelve el texto literal con su
    sección y URL. Úsala ante cualquier duda tuya o del usuario sobre cómo se rellena una
    casilla, qué significa un concepto o un plazo, en lugar de responder de memoria.
    Solo descarga páginas públicas; no envía datos."""
    with _servicio() as s:
        return s.consultar_instrucciones_303(trimestre, consulta, max_resultados)


@mcp.tool
def info_casilla(
    casilla: Annotated[str, Field(description="Número de casilla, p. ej. '28' o '71'.")],
    periodo: Annotated[str, Field(description="303: trimestre '2027-1T'. 390: ejercicio '2026'.")],
    modelo: Annotated[Literal["303", "390"], Field(description="Modelo al que pertenece la casilla.")] = "303",
) -> dict[str, Any]:
    """Qué es una casilla según el diseño de registro oficial aplicable (página, descripción,
    formato) y si la herramienta la calcula o queda fuera de su alcance."""
    with _servicio() as s:
        return s.info_casilla(casilla, periodo, modelo)


@mcp.tool
def plazos(hoy: Annotated[str | None, Field(description="Fecha de referencia AAAA-MM-DD; por defecto hoy.")] = None) -> list[dict[str, Any]]:
    """Próximos plazos de presentación del 303 (inicio, fin y fin de domiciliación).
    Úsala para saber qué trimestre toca declarar y hasta cuándo."""
    with _servicio() as s:
        return s.plazos(hoy)


@mcp.tool
def ver_perfil(
    trimestre: Annotated[str | None, Field(description="303: trimestre '2027-1T'. 390: ejercicio '2026'.")] = None,
    modelo: Annotated[Literal["303", "390"], Field(description="Para qué declaración se revisa el perfil.")] = "303",
) -> dict[str, Any]:
    """Perfil fiscal del declarante (NIF, nombre, situación, forma de pago, IBAN, datos del 390...),
    las preguntas pendientes (con dónde mirar cada dato), los problemas que impiden
    generar la declaración y las fuentes recomendadas. Úsala al empezar cada declaración."""
    with _servicio() as s:
        return s.ver_perfil(trimestre, modelo)


@mcp.tool
def actualizar_perfil(
    cambios: Annotated[dict[str, Any], Field(description="Campos a cambiar (ver preguntas_pendientes en ver_perfil). null = sin confirmar.")],
    motivo: Annotated[str | None, Field(description="De dónde sale el dato: respuesta del usuario, justificante del 303 de X...")] = None,
) -> dict[str, Any]:
    """Guarda datos del perfil fiscal que el usuario te ha dado o que has leído de sus
    documentos (último 303, declaración censal). Valida NIF e IBAN. No guardes nada que
    hayas supuesto: si no se sabe, déjalo sin confirmar y pregunta."""
    with _servicio() as s:
        return s.actualizar_perfil(cambios, motivo)


@mcp.tool
def confirmar_perfil(
    trimestre: Trimestre,
    fuente: Annotated[str, Field(description="Cómo se ha confirmado: 'el usuario confirma que no ha cambiado nada', 'justificante del 303 2026-3T'...")],
) -> dict[str, Any]:
    """Registra que el USUARIO ha confirmado que su perfil (situación, forma de pago, IBAN,
    cuotas a compensar) sigue vigente para este trimestre. Obligatorio en cada trimestre
    antes de generar el 303. Llámala solo después de repasarlo con él."""
    with _servicio() as s:
        return s.confirmar_perfil(trimestre, fuente)


@mcp.tool
def registrar_factura(
    datos: Annotated[dict[str, Any], Field(description=(
        "Factura: tipo ('emitida'|'recibida'), numero, fecha (AAAA-MM-DD, expedición), nif_emisor, nombre_emisor, "
        "nif_receptor, nombre_receptor, lineas [{base, tipo_iva, cuota}], retencion_irpf (positivo, 0 si no hay), "
        "total. Opcionales: fecha_operacion, rectificativa, simplificada (ticket), bien_inversion, "
        "inversion_sujeto_pasivo, recargo_equivalencia, afecta_actividad (recibidas: true si el gasto es de la "
        "actividad; pregúntalo), moneda, concepto. Importes como números o textos con decimales."
    ))],
    ruta_pdf: Annotated[str | None, Field(description="Ruta local del PDF. Se usa para deduplicar y para verificar que los datos aparecen en él.")] = None,
    origen: Annotated[str | None, Field(description="De dónde sale la factura (carpeta, email de X con fecha...).")] = None,
    trimestre: Annotated[str | None, Field(description="Trimestre que estás preparando, para avisar si la factura es de otro.")] = None,
) -> dict[str, Any]:
    """Registra en el libro una factura cuyos datos has leído (de un PDF, un email...).
    La tool valida NIF, aritmética (base × tipo = cuota; base + IVA − retención = total),
    alcance soportado, duplicados y que los datos aparecen en el PDF. Si algo no cuadra,
    la factura queda 'pendiente' y no entra en el 303 hasta resolverlo."""
    with _servicio() as s:
        return s.registrar_factura(datos, ruta_pdf, origen, trimestre)


@mcp.tool
def listar_facturas(
    trimestre: Trimestre | None = None,
    estado: Annotated[Literal["valida", "pendiente", "descartada"] | None, Field(description="Filtrar por estado.")] = None,
) -> dict[str, Any]:
    """Facturas del libro registro, con su estado e incidencias. Úsala para revisar qué
    hay registrado y qué queda pendiente antes de calcular."""
    with _servicio() as s:
        return s.listar_facturas(trimestre, estado)


@mcp.tool
def corregir_factura(
    factura_id: int,
    cambios: Annotated[dict[str, Any], Field(description="Campos de la factura a cambiar (mismo formato que registrar_factura).")],
    motivo: Motivo,
) -> dict[str, Any]:
    """Corrige datos de una factura registrada (p. ej. un importe mal leído o afecta_actividad).
    Se vuelve a validar y queda registrado el antes/después con el motivo."""
    with _servicio() as s:
        return s.corregir_factura(factura_id, cambios, motivo)


@mcp.tool
def confirmar_factura(factura_id: int, motivo: Motivo) -> dict[str, Any]:
    """Acepta los avisos de nivel 'revisar' de una factura cuando el USUARIO ha comprobado
    que es correcta. No sirve para errores aritméticos ni para casos fuera de alcance."""
    with _servicio() as s:
        return s.confirmar_factura(factura_id, motivo)


@mcp.tool
def descartar_factura(factura_id: int, motivo: Motivo) -> dict[str, Any]:
    """Saca una factura de los cálculos (no se borra; queda en el historial).
    P. ej. si no es una factura, es de otro titular o el usuario la quiere excluir."""
    with _servicio() as s:
        return s.descartar_factura(factura_id, motivo)


@mcp.tool
def reactivar_factura(factura_id: int, motivo: Motivo) -> dict[str, Any]:
    """Vuelve a incluir una factura descartada."""
    with _servicio() as s:
        return s.reactivar_factura(factura_id, motivo)


@mcp.tool
def historial_factura(factura_id: int) -> dict[str, Any]:
    """Historial completo de cambios de una factura (altas, correcciones, confirmaciones, descartes)."""
    with _servicio() as s:
        return s.historial_factura(factura_id)


@mcp.tool
def comprobar_diseno_303(trimestre: Trimestre) -> dict[str, Any]:
    """Comprueba en la web de la AEAT si el diseño de registro del 303 aplicable a ese
    trimestre es el que está instalado. Llámala SIEMPRE antes de generar un 303.
    Solo descarga información pública; no envía datos. Si devuelve estado 'nuevo',
    revisa 'compatibilidad' y 'diferencias' y usa instalar_diseno_303."""
    with _servicio() as s:
        return s.comprobar_diseno_303(trimestre)


@mcp.tool
def instalar_diseno_303(
    trimestre: Trimestre | None = None,
    ruta_xlsx: Annotated[str | None, Field(description="Excel oficial descargado a mano (alternativa a descargarlo).")] = None,
    desde: Annotated[str | None, Field(description="Trimestre desde el que aplica, si no se puede deducir.")] = None,
) -> dict[str, Any]:
    """Descarga e instala el diseño de registro vigente de la AEAT (o uno local).
    Devuelve si la herramienta es compatible con él. Si no lo es, NO generes el 303:
    explícale al usuario qué ha cambiado."""
    with _servicio() as s:
        return s.instalar_diseno_303(trimestre, ruta_xlsx, desde)


@mcp.tool
def calcular_303(
    trimestre: Trimestre,
    opcion_negativo: Annotated[Literal["compensar", "devolver"] | None, Field(description="Solo 4T con resultado negativo: decisión del usuario.")] = None,
) -> dict[str, Any]:
    """Calcula las casillas del 303 a partir del libro registro y del perfil, con la
    explicación de cada importe, avisos y bloqueos. No escribe ningún fichero.
    Usa su salida para explicar el resultado al usuario; no recalcules nada."""
    with _servicio() as s:
        return s.calcular_303(trimestre, opcion_negativo)


@mcp.tool
def generar_303(
    trimestre: Trimestre,
    opcion_negativo: Annotated[Literal["compensar", "devolver"] | None, Field(description="Solo 4T con resultado negativo.")] = None,
    ignorar_pendientes: Annotated[bool, Field(description="Generar dejando fuera las facturas pendientes. Solo si el usuario lo pide expresamente.")] = False,
) -> dict[str, Any]:
    """Genera el fichero .303 para importar en la Sede de la AEAT con el diseño de registro
    que corresponde al trimestre. Se niega si hay bloqueos (facturas pendientes, datos de
    perfil que faltan). Devuelve la ruta, las casillas y los pasos para presentarlo."""
    with _servicio() as s:
        return s.generar_303(trimestre, opcion_negativo, ignorar_pendientes)


@mcp.tool
def registrar_303_presentado(
    trimestre: Trimestre,
    casillas: Annotated[dict[str, Any], Field(description=(
        "Casillas con importe tal como aparecen en el justificante: {'07': 300, '09': 63, '27': 63, "
        "'46': 63, '64': 63, '65': 100, '66': 63, '69': 63, '71': 63}. Las vacías se omiten. "
        "Siempre la 71 (resultado), aunque sea 0."
    ))],
    tipo_declaracion: Annotated[str, Field(description=(
        "I ingreso, U domiciliación, N sin actividad/resultado cero, C compensar, D devolver. "
        "En el justificante: 'NEGATIVA/SIN ACTIVIDAD/RESULTADO CERO' = N; 'DOMICILIACIÓN' = U."
    ))],
    justificante: Annotated[str, Field(description="Número de justificante (13 dígitos).")],
    fecha_presentacion: Annotated[str | None, Field(description="Fecha de 'Presentación realizada el' (dd-mm-aaaa).")] = None,
    ruta_pdf: Annotated[str | None, Field(description="Ruta del justificante PDF: se comprueba que los datos aparecen en él y se guarda una copia.")] = None,
    sin_actividad: Annotated[bool | None, Field(description="True si el justificante marca 'Sin actividad'.")] = None,
) -> dict[str, Any]:
    """Guarda un 303 YA PRESENTADO en el libro local, igual que los que genera la herramienta:
    tanto los generados aquí (tras presentarlos) como los que el usuario presentó a mano antes.
    Valida la aritmética entre casillas y que los datos aparecen en el PDF. Los usa el 390."""
    with _servicio() as s:
        return s.registrar_303_presentado(trimestre, casillas, tipo_declaracion, justificante,
                                          fecha_presentacion, ruta_pdf, sin_actividad)


@mcp.tool
def marcar_303_no_presentado(trimestre: Trimestre, motivo: Motivo) -> dict[str, Any]:
    """Deja constancia de que en ese trimestre no se presentó 303 porque no correspondía
    (p. ej. aún no estaba dado de alta en la actividad). Solo con confirmación del usuario."""
    with _servicio() as s:
        return s.marcar_303_no_presentado(trimestre, motivo)


@mcp.tool
def listar_autoliquidaciones(
    ejercicio: Annotated[int | None, Field(description="Ejercicio, p. ej. 2026.")] = None,
    modelo: Annotated[Literal["303", "390"] | None, Field(description="Filtrar por modelo.")] = None,
) -> dict[str, Any]:
    """Autoliquidaciones guardadas (generadas, presentadas o marcadas como no presentadas),
    con sus casillas, justificante y PDF. Úsala para ver qué 303 faltan antes del 390."""
    with _servicio() as s:
        return s.listar_autoliquidaciones(ejercicio, modelo)


Ejercicio = Annotated[int, Field(description="Ejercicio (año) de la declaración, p. ej. 2026.")]


@mcp.tool
def comprobar_diseno_390(ejercicio: Ejercicio) -> dict[str, Any]:
    """Comprueba en la web de la AEAT si el diseño de registro del 390 aplicable al ejercicio es
    el instalado. Llámala SIEMPRE antes de generar un 390. Solo descarga información pública."""
    with _servicio() as s:
        return s.comprobar_diseno_390(ejercicio)


@mcp.tool
def instalar_diseno_390(
    ejercicio: Ejercicio | None = None,
    ruta_xlsx: Annotated[str | None, Field(description="Excel oficial descargado a mano (alternativa a descargarlo).")] = None,
    desde: Annotated[str | None, Field(description="Periodo desde el que aplica (p. ej. '2027-1T'), si no se puede deducir.")] = None,
) -> dict[str, Any]:
    """Descarga e instala el diseño de registro vigente del 390 (o uno local) y dice si la
    herramienta es compatible. Si no lo es, NO generes el 390: explica el cambio al usuario."""
    with _servicio() as s:
        return s.instalar_diseno_390(ejercicio, ruta_xlsx, desde)


@mcp.tool
def consultar_instrucciones_390(
    ejercicio: Ejercicio,
    consulta: Annotated[str | None, Field(description="Casilla ('casilla 95') o concepto ('volumen de operaciones'). Vacío = índice.")] = None,
    max_resultados: Annotated[int, Field(ge=1, le=15)] = 6,
) -> dict[str, Any]:
    """Busca en las INSTRUCCIONES OFICIALES del modelo 390 del ejercicio (PDF de la ficha G412 de
    la Sede) y devuelve el texto literal con su apartado y URL. Úsala ante cualquier duda sobre el 390."""
    with _servicio() as s:
        return s.consultar_instrucciones_390(ejercicio, consulta, max_resultados)


@mcp.tool
def calcular_390(ejercicio: Ejercicio) -> dict[str, Any]:
    """Calcula el 390 del ejercicio a partir del libro registro y de los 303 presentados (cruzándolos),
    con la explicación de cada casilla, el estado de cada trimestre, avisos y bloqueos. No escribe ficheros."""
    with _servicio() as s:
        return s.calcular_390(ejercicio)


@mcp.tool
def generar_390(ejercicio: Ejercicio) -> dict[str, Any]:
    """Genera el fichero .390 para importar en la Sede con el diseño de registro del ejercicio.
    Se niega si hay bloqueos (303 sin registrar, libro que no cuadra, datos del perfil que faltan)."""
    with _servicio() as s:
        return s.generar_390(ejercicio)


@mcp.prompt
def iva_trimestral(trimestre: str) -> str:
    """Prepara el 303 de un trimestre siguiendo el flujo de gestoría."""
    return f"Prepárame el modelo 303 del trimestre {trimestre}.\n\n{INSTRUCCIONES}"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
