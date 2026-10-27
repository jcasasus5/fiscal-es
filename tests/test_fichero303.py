"""El fichero generado cumple el diseño de registro oficial (leído del Excel de la AEAT)."""

import re
from decimal import Decimal

import pytest

from conftest import IBAN_PRUEBA, NIF_YO, factura_emitida, factura_recibida
from fiscal_es.core import diseno, fichero303
from fiscal_es.core.periodo import Trimestre


@pytest.fixture(scope="module")
def d2026():
    return diseno.cargar(diseno.seleccionar(Trimestre(2026, 3), None))


def _leer(path):
    return open(path, "rb").read()


def _estructura(d, contenido: bytes):
    texto = contenido.decode("iso-8859-1")
    assert "\n" not in texto and "\r" not in texto
    # Cabecera y cierre
    assert texto.startswith("<T303020263T0000><AUX>")
    assert texto.endswith("</T303020263T0000>")
    leido = fichero303.leer(d, contenido)
    assert set(leido) == {"01", "03", "DID"}
    for cod, valores in leido.items():
        pag = d.paginas[cod]
        reg = valores["__registro__"]
        assert len(reg) == pag.total
        for c in pag.campos:
            trozo = reg[c.pos - 1 : c.pos - 1 + c.lon]
            tipo = c.tipo.strip()
            if c.constante is not None and not c.casilla:
                assert trozo == c.constante.ljust(c.lon), (cod, c.descripcion)
            if tipo == "Num":
                assert re.fullmatch(r"\d+| +", trozo), (cod, c.descripcion, trozo)
            elif tipo == "N":
                assert re.fullmatch(r"N?\d+", trozo), (cod, c.descripcion, trozo)
            elif tipo in ("An", "A"):
                assert re.fullmatch(r"[A-Z0-9ÑÇ <>/]*", trozo), (cod, c.descripcion, trozo)
    # Longitud total = cabecera fija + páginas + cierre
    cab = d.paginas["00"]
    fijo = sum(c.lon for c in cab.campos if c.lon)
    assert len(texto) == fijo + sum(d.paginas[c].total for c in ("01", "03", "DID"))
    return leido


def test_sin_actividad(svc, d2026):
    g = svc.generar_303("2026-3T")
    assert g["generado"]
    leido = _estructura(d2026, _leer(g["fichero"]))
    p1, p3, did = leido["01"], leido["03"], leido["DID"]
    assert p1["tipo_declaracion"] == "N"
    assert p1["nif"] == NIF_YO
    assert p1["nombre"].rstrip() == "FICTICIO EJEMPLO AUTONOMO"
    assert (p1["ejercicio"], p1["periodo"]) == ("2026", "3T")
    assert p3["sin_actividad"] == "X"
    assert p3["[65]"] == "10000"  # 100,00 %
    assert p3["[71]"] == "0" * 17
    assert p1["[08]"] == "02100"  # tipo constante del diseño
    assert did["iban"].strip() == ""  # sin ingreso no va IBAN
    # Casillas de identificación fuera del 4T (notas 3, 4, 6 y 8 del diseño)
    assert (p1["exonerado_390"], p1["volumen_distinto_cero"], p1["prorrata_opcion"], p1["gasolinas"]) == ("0", "0", "2", "0")


def test_con_importes_y_domiciliacion(svc, d2026):
    svc.registrar_factura(factura_emitida(base="1234.56", cuota="259.26", retencion="185.18", total="1308.64"))
    g = svc.generar_303("2026-3T")
    leido = _estructura(d2026, _leer(g["fichero"]))
    p1, p3, did = leido["01"], leido["03"], leido["DID"]
    # Importes en céntimos, 17 posiciones alineadas a la derecha con ceros
    assert p1["[07]"] == "00000000000123456"
    assert p1["[09]"] == "00000000000025926"
    assert p3["[71]"] == "00000000000025926"
    assert p1["tipo_declaracion"] == "U" and p3["sin_actividad"] == " "
    assert did["iban"].strip() == IBAN_PRUEBA


def test_negativo_con_signo(svc, d2026):
    svc.registrar_factura(factura_recibida())
    g = svc.generar_303("2026-3T")
    leido = _estructura(d2026, _leer(g["fichero"]))
    # [46] es de tipo N: negativo con 'N' en la primera posición
    assert leido["01"]["[46]"] == "N" + "2100".zfill(16)
    assert leido["01"]["tipo_declaracion"] == "C"


def test_formatear_errores(d2026):
    campo = fichero303.campo(d2026.paginas["01"], fichero303.ESPEC, "[07]")
    with pytest.raises(fichero303.ErrorDiseno):
        fichero303.formatear(campo, Decimal("-1"))  # [07] es Num: sin signo
    with pytest.raises(fichero303.ErrorDiseno):
        fichero303.formatear(campo, Decimal("1" * 16))  # no cabe


def test_texto_aeat():
    assert fichero303._texto_aeat("Núñez-Gómez, José Ángel") == "NUÑEZ GOMEZ JOSE ANGEL"
