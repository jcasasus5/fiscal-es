from datetime import date
from decimal import Decimal

import pytest

from fiscal_es.core import iban, nif
from fiscal_es.core.importes import formato_es, parse_importe
from fiscal_es.core.periodo import Trimestre, plazo_303, proximos_plazos


@pytest.mark.parametrize(
    "valor,tipo",
    [
        ("12345678Z", "DNI"),
        ("12345678-z", "DNI"),
        ("X1234567L", "NIE"),
        ("B12345674", "CIF"),
        ("ESB12345674", "CIF"),
        ("A58818501", "CIF"),
        ("12345678A", None),  # letra incorrecta
        ("B12345675", None),  # control incorrecto
        ("FR12345678901", None),
    ],
)
def test_nif(valor, tipo):
    assert nif.tipo(valor) == tipo


def test_nif_extranjero():
    assert nif.parece_extranjero("FR40303265045")
    assert nif.parece_extranjero("DE123456789")
    assert not nif.parece_extranjero("B12345674")
    assert not nif.parece_extranjero("X1234567L")


def test_iban():
    assert iban.es_valido("ES91 2100 0418 4502 0005 1332")
    assert not iban.es_valido("ES9221000418450200051332")


@pytest.mark.parametrize(
    "texto,esperado",
    [("1.234,56", "1234.56"), ("1234.56", "1234.56"), ("1,234.56", "1234.56"), ("12,34 €", "12.34"), (300, "300"), (0.1, "0.1")],
)
def test_parse_importe(texto, esperado):
    assert parse_importe(texto) == Decimal(esperado)


def test_formato_es():
    assert formato_es(Decimal("1800")) == "1.800,00"
    assert formato_es(Decimal("-12.34")) == "-12,34"


def test_trimestre():
    t = Trimestre.parse("2027-1T")
    assert t == Trimestre.parse("1T 2027") == Trimestre(2027, 1)
    assert t.inicio == date(2027, 1, 1) and t.fin == date(2027, 3, 31)
    assert Trimestre(2026, 4).siguiente() == t
    assert str(Trimestre.de_fecha(date(2026, 8, 12))) == "2026-3T"
    with pytest.raises(ValueError):
        Trimestre.parse("2027-5T")


def test_plazos():
    # 3T 2026: martes 20/10/2026, domiciliación hasta el 15.
    p = plazo_303(Trimestre(2026, 3))
    assert (p.inicio, p.fin, p.fin_domiciliacion) == (date(2026, 10, 1), date(2026, 10, 20), date(2026, 10, 15))
    # 4T 2026: el 30/01/2027 es sábado -> lunes 01/02/2027. Domiciliación hasta el 25 de enero.
    p = plazo_303(Trimestre(2026, 4))
    assert (p.fin, p.fin_domiciliacion) == (date(2027, 2, 1), date(2027, 1, 25))
    # El 24/10/2026 el siguiente plazo abierto es el del 4T.
    assert str(proximos_plazos(date(2026, 10, 24))[0].trimestre) == "2026-4T"
    assert str(proximos_plazos(date(2027, 4, 3))[0].trimestre) == "2027-1T"


@pytest.mark.parametrize("valor", ["", "${FISCAL_DATA_DIR:-~/fiscal-data}", "${FISCAL_DATA_DIR}", "$FISCAL_DATA_DIR", "relativa/datos"])
def test_fiscal_data_dir_no_expandido_usa_defecto(monkeypatch, tmp_path, valor):
    """Si el agente no expande la variable, no se crea una carpeta con el texto literal."""
    from fiscal_es import config

    monkeypatch.setattr(config, "DEFECTO", tmp_path / "defecto")
    monkeypatch.setenv("FISCAL_DATA_DIR", valor)
    assert config.rutas().base == tmp_path / "defecto"


def test_fiscal_data_dir_absoluto(monkeypatch, tmp_path):
    from fiscal_es import config

    monkeypatch.setenv("FISCAL_DATA_DIR", str(tmp_path / "mis-datos"))
    assert config.rutas().base == tmp_path / "mis-datos"
