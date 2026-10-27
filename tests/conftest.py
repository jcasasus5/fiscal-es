"""Fixtures comunes. Todos los datos son ficticios; los PDF se generan al vuelo
(no hay PDFs en el repo: *.pdf está en .gitignore)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fiscal_es.servicio import Servicio

# NIF/CIF ficticios con dígito de control válido
NIF_YO = "12345678Z"
NIF_CLIENTE = "B12345674"  # CIF ficticio
NIF_PROVEEDOR = "A58818501"  # CIF ficticio
IBAN_PRUEBA = "ES9121000418450200051332"  # IBAN de ejemplo (formato válido)


def generar_pdf(ruta: Path, lineas_texto: list[str]) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(ruta), pagesize=A4)
    y = 800
    for linea in lineas_texto:
        c.drawString(60, y, linea)
        y -= 18
    c.save()
    return ruta


def pdf_factura(ruta: Path, *, numero: str, fecha: str, emisor: tuple[str, str], receptor: tuple[str, str],
                base: str, tipo: str, cuota: str, retencion: str | None, total: str, extra: list[str] | None = None) -> Path:
    texto = [
        f"FACTURA {numero}",
        f"Fecha: {fecha}",
        f"Emisor: {emisor[0]}  NIF: {emisor[1]}",
        f"Cliente: {receptor[0]}  NIF: {receptor[1]}",
        "Concepto: Servicios profesionales",
        f"Base imponible: {base} EUR",
        f"IVA {tipo}%: {cuota} EUR",
    ]
    if retencion:
        texto.append(f"Retencion IRPF 15%: -{retencion} EUR")
    texto.append(f"TOTAL: {total} EUR")
    texto += extra or []
    return generar_pdf(ruta, texto)


def factura_emitida(numero: str = "2027-001", fecha: str = "2026-08-10", base="1000.00", cuota="210.00",
                    retencion="150.00", total="1060.00", tipo_iva="21", **extra) -> dict:
    d = {
        "tipo": "emitida",
        "numero": numero,
        "fecha": fecha,
        "nif_emisor": NIF_YO,
        "nombre_emisor": "Autonomo Ficticio",
        "nif_receptor": NIF_CLIENTE,
        "nombre_receptor": "Cliente Ficticio SL",
        "lineas": [{"base": base, "tipo_iva": tipo_iva, "cuota": cuota}],
        "retencion_irpf": retencion,
        "total": total,
    }
    d.update(extra)
    return d


def factura_recibida(numero: str = "P-77", fecha: str = "2026-09-05", base="100.00", cuota="21.00",
                     total="121.00", **extra) -> dict:
    d = {
        "tipo": "recibida",
        "numero": numero,
        "fecha": fecha,
        "nif_emisor": NIF_PROVEEDOR,
        "nombre_emisor": "Proveedor Ficticio SA",
        "nif_receptor": NIF_YO,
        "nombre_receptor": "Autonomo Ficticio",
        "lineas": [{"base": base, "tipo_iva": "21", "cuota": cuota}],
        "retencion_irpf": "0",
        "total": total,
        "afecta_actividad": True,
    }
    d.update(extra)
    return d


@pytest.fixture
def data_dir(tmp_path, monkeypatch) -> Path:
    d = tmp_path / "fiscal-data"
    monkeypatch.setenv("FISCAL_DATA_DIR", str(d))
    return d


PERFIL_COMPLETO = {
    "nif": NIF_YO,
    "nombre": "Ficticio Ejemplo, Autónomo",
    "regimen": "general",
    "periodicidad": "trimestral",
    "territorio": "comun",
    "criterio_caja": False,
    "destinatario_criterio_caja": False,
    "sii": False,
    "registro_devolucion_mensual": False,
    "prorrata": False,
    "concurso_acreedores": False,
    "forma_pago": "domiciliacion",
    "iban": IBAN_PRUEBA,
    "cuotas_a_compensar": "0",
}


PERFIL_390 = {
    "exonerado_390": False,
    "apellidos": "Ficticio Ejemplo",
    "nombre_pila": "Autónomo",
    "actividad_principal": "Consultoría ficticia",
    "clave_actividad": "A05",
    "epigrafe_iae": "0000",
    "operaciones_347": False,
}


def pdf_justificante(ruta: Path, *, justificante: str, trimestre: str, casillas: dict[str, str], sin_actividad=False) -> Path:
    """Justificante ficticio con el aspecto (texto) del que da la Sede tras presentar un 303."""
    texto = [
        "INFORMACIÓN DE LA PRESENTACIÓN DE LA DECLARACIÓN",
        "Modelo 303",
        "Presentación realizada el: 15-10-2026 a las 10:00:00",
        f"Número de justificante: {justificante}",
        f"NIF Presentador: {NIF_YO}",
        f"Periodo {trimestre}",
    ]
    texto += [f"Casilla {c}: {v}" for c, v in casillas.items()]
    if sin_actividad:
        texto.append("NEGATIVA/SIN ACTIVIDAD/RESULTADO CERO")
    return generar_pdf(ruta, texto)


@pytest.fixture
def svc(data_dir) -> Servicio:
    s = Servicio(data_dir)
    s.actualizar_perfil(PERFIL_COMPLETO, "datos ficticios de test")
    s.confirmar_perfil("2026-3T", "test")
    yield s
    s.close()
