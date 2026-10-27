"""CLI: los mismos casos de uso que el servidor MCP, sin agente."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import typer

from .servicio import Servicio

app = typer.Typer(help="Modelo 303 para autónomos: libro registro, cálculo y fichero para importar en la Sede.",
                  no_args_is_help=True)
perfil_app = typer.Typer(help="Perfil fiscal del declarante.", no_args_is_help=True)
factura_app = typer.Typer(help="Libro registro de facturas.", no_args_is_help=True)
diseno_app = typer.Typer(help="Diseño de registro oficial del 303.", no_args_is_help=True)
app.add_typer(perfil_app, name="perfil")
app.add_typer(factura_app, name="factura")
app.add_typer(diseno_app, name="diseno")

DatosOpt = typer.Option(None, "--data-dir", help="Directorio de datos (por defecto FISCAL_DATA_DIR o ~/fiscal-data).")


def _svc(data_dir: Optional[Path]) -> Servicio:
    return Servicio(data_dir)


def _out(obj: Any) -> None:
    typer.echo(json.dumps(obj, ensure_ascii=False, indent=2))


def _json_arg(texto: str) -> dict[str, Any]:
    p = Path(texto)
    if p.suffix == ".json" and p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return json.loads(texto)


@perfil_app.command("ver")
def perfil_ver(trimestre: Optional[str] = typer.Argument(None, help="303: '2027-1T'; 390: '2026'"),
               modelo: str = typer.Option("303", help="303 o 390"), data_dir: Optional[Path] = DatosOpt) -> None:
    _out(_svc(data_dir).ver_perfil(trimestre, modelo))


@perfil_app.command("set")
def perfil_set(cambios: str = typer.Argument(..., help="JSON con los campos a cambiar, o ruta a un .json"),
               motivo: Optional[str] = typer.Option(None), data_dir: Optional[Path] = DatosOpt) -> None:
    _out(_svc(data_dir).actualizar_perfil(_json_arg(cambios), motivo))


@perfil_app.command("confirmar")
def perfil_confirmar(trimestre: str, fuente: str = typer.Option(..., help="Cómo se ha confirmado"),
                     data_dir: Optional[Path] = DatosOpt) -> None:
    """Confirma que el perfil sigue vigente para el trimestre (obligatorio cada trimestre)."""
    _out(_svc(data_dir).confirmar_perfil(trimestre, fuente))


@factura_app.command("registrar")
def factura_registrar(datos: str = typer.Argument(..., help="JSON de la factura, o ruta a un .json"),
                      pdf: Optional[Path] = typer.Option(None, help="PDF de la factura"),
                      trimestre: Optional[str] = typer.Option(None), data_dir: Optional[Path] = DatosOpt) -> None:
    _out(_svc(data_dir).registrar_factura(_json_arg(datos), str(pdf) if pdf else None, "cli", trimestre))


@factura_app.command("listar")
def factura_listar(trimestre: Optional[str] = typer.Argument(None), estado: Optional[str] = typer.Option(None),
                   data_dir: Optional[Path] = DatosOpt) -> None:
    _out(_svc(data_dir).listar_facturas(trimestre, estado))


@factura_app.command("corregir")
def factura_corregir(id: int, cambios: str, motivo: str = typer.Option(...), data_dir: Optional[Path] = DatosOpt) -> None:
    _out(_svc(data_dir).corregir_factura(id, _json_arg(cambios), motivo))


@factura_app.command("confirmar")
def factura_confirmar(id: int, motivo: str = typer.Option(...), data_dir: Optional[Path] = DatosOpt) -> None:
    _out(_svc(data_dir).confirmar_factura(id, motivo))


@factura_app.command("descartar")
def factura_descartar(id: int, motivo: str = typer.Option(...), data_dir: Optional[Path] = DatosOpt) -> None:
    _out(_svc(data_dir).descartar_factura(id, motivo))


@factura_app.command("historial")
def factura_historial(id: int, data_dir: Optional[Path] = DatosOpt) -> None:
    _out(_svc(data_dir).historial_factura(id))


@diseno_app.command("comprobar")
def diseno_comprobar(periodo: str = typer.Argument(..., help="303: '2027-1T'; 390: '2026'"),
                     modelo: str = typer.Option("303", help="303 o 390"), data_dir: Optional[Path] = DatosOpt) -> None:
    svc = _svc(data_dir)
    _out(svc.comprobar_diseno_390(int(periodo[:4])) if modelo == "390" else svc.comprobar_diseno_303(periodo))


@diseno_app.command("instalar")
def diseno_instalar(trimestre: Optional[str] = typer.Argument(None),
                    xlsx: Optional[Path] = typer.Option(None, help="Excel oficial descargado a mano"),
                    desde: Optional[str] = typer.Option(None, help="Trimestre desde el que aplica, p. ej. 2027-1T"),
                    data_dir: Optional[Path] = DatosOpt) -> None:
    _out(_svc(data_dir).instalar_diseno_303(trimestre, str(xlsx) if xlsx else None, desde))


@diseno_app.command("listar")
def diseno_listar(data_dir: Optional[Path] = DatosOpt) -> None:
    _out(_svc(data_dir).disenos_instalados())


@app.command("calcular-303")
def calcular_303(trimestre: str, opcion_negativo: Optional[str] = typer.Option(None, help="4T: compensar | devolver"),
                 data_dir: Optional[Path] = DatosOpt) -> None:
    """Calcula las casillas sin generar el fichero."""
    _out(_svc(data_dir).calcular_303(trimestre, opcion_negativo))


@app.command("generar-303")
def generar_303(trimestre: str, opcion_negativo: Optional[str] = typer.Option(None, help="4T: compensar | devolver"),
                ignorar_pendientes: bool = typer.Option(False, help="Generar dejando fuera las facturas pendientes"),
                data_dir: Optional[Path] = DatosOpt) -> None:
    """Genera el fichero .303 para importar en la Sede de la AEAT."""
    res = _svc(data_dir).generar_303(trimestre, opcion_negativo, ignorar_pendientes)
    _out(res)
    if not res.get("generado"):
        raise typer.Exit(1)


@app.command("capacidades")
def capacidades(data_dir: Optional[Path] = DatosOpt) -> None:
    """Qué está soportado y qué no."""
    _out(_svc(data_dir).capacidades())


@app.command("instrucciones")
def instrucciones(trimestre: str, consulta: Optional[str] = typer.Argument(None, help="Casilla o concepto; vacío = índice"),
                  max_resultados: int = typer.Option(6), data_dir: Optional[Path] = DatosOpt) -> None:
    """Busca en las instrucciones oficiales de la AEAT del ejercicio."""
    _out(_svc(data_dir).consultar_instrucciones_303(trimestre, consulta, max_resultados))


@app.command("casilla")
def casilla(numero: str, periodo: str = typer.Argument(..., help="303: '2027-1T'; 390: '2026'"),
            modelo: str = typer.Option("303", help="303 o 390"), data_dir: Optional[Path] = DatosOpt) -> None:
    """Qué es una casilla según el diseño de registro y si la calcula la herramienta."""
    _out(_svc(data_dir).info_casilla(numero, periodo, modelo))


autoliq_app = typer.Typer(help="Autoliquidaciones generadas y presentadas.", no_args_is_help=True)
app.add_typer(autoliq_app, name="autoliquidacion")


@autoliq_app.command("registrar-303")
def autoliq_registrar_303(trimestre: str, casillas: str = typer.Argument(..., help="JSON {casilla: importe} o ruta a .json"),
                          tipo: str = typer.Option(..., help="I, U, N, C o D"),
                          justificante: str = typer.Option(...), fecha: Optional[str] = typer.Option(None),
                          pdf: Optional[Path] = typer.Option(None), sin_actividad: Optional[bool] = typer.Option(None),
                          data_dir: Optional[Path] = DatosOpt) -> None:
    """Registra un 303 ya presentado a partir de su justificante."""
    _out(_svc(data_dir).registrar_303_presentado(trimestre, _json_arg(casillas), tipo, justificante, fecha,
                                                 str(pdf) if pdf else None, sin_actividad, "cli"))


@autoliq_app.command("no-presentado-303")
def autoliq_no_presentado(trimestre: str, motivo: str = typer.Option(...), data_dir: Optional[Path] = DatosOpt) -> None:
    _out(_svc(data_dir).marcar_303_no_presentado(trimestre, motivo))


@autoliq_app.command("listar")
def autoliq_listar(ejercicio: Optional[int] = typer.Argument(None), modelo: Optional[str] = typer.Option(None),
                   data_dir: Optional[Path] = DatosOpt) -> None:
    _out(_svc(data_dir).listar_autoliquidaciones(ejercicio, modelo))


@app.command("calcular-390")
def calcular_390(ejercicio: int, data_dir: Optional[Path] = DatosOpt) -> None:
    """Calcula el 390 sin generar el fichero."""
    _out(_svc(data_dir).calcular_390(ejercicio))


@app.command("generar-390")
def generar_390(ejercicio: int, data_dir: Optional[Path] = DatosOpt) -> None:
    """Genera el fichero .390 para importar en la Sede de la AEAT."""
    res = _svc(data_dir).generar_390(ejercicio)
    _out(res)
    if not res.get("generado"):
        raise typer.Exit(1)


@app.command("instrucciones-390")
def instrucciones_390(ejercicio: int, consulta: Optional[str] = typer.Argument(None),
                      max_resultados: int = typer.Option(6), data_dir: Optional[Path] = DatosOpt) -> None:
    """Busca en las instrucciones oficiales del 390 del ejercicio."""
    _out(_svc(data_dir).consultar_instrucciones_390(ejercicio, consulta, max_resultados))


@app.command("plazos")
def plazos(hoy: Optional[str] = typer.Option(None, help="Fecha de referencia (AAAA-MM-DD)"),
           data_dir: Optional[Path] = DatosOpt) -> None:
    _out(_svc(data_dir).plazos(hoy))


if __name__ == "__main__":
    app()
