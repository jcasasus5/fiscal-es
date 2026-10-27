"""Modelo 390: registro de los 303 presentados, cálculo anual (resultados hechos a mano),
fichero frente al diseño oficial e instrucciones en PDF."""

import re

import pytest

from conftest import PERFIL_390, factura_emitida, factura_recibida, pdf_justificante
from fiscal_es.core import diseno, fichero, fichero390, instrucciones_aeat
from fiscal_es.core.periodo import Trimestre

J = {1: "3030000000011", 2: "3030000000022", 3: "3030000000033", 4: "3030000000044"}


@pytest.fixture
def svc390(svc):
    svc.actualizar_perfil(PERFIL_390, "test")
    svc.confirmar_perfil("2026-4T", "test")
    return svc


def sin_actividad(svc, n):
    return svc.registrar_303_presentado(f"2026-{n}T", {"65": "100", "71": "0"}, "N", J[n], "15-04-2026", sin_actividad=True)


def cas(r, pag, c):
    return r["casillas"].get(pag, {}).get(c, "0,00")


# ----------------------------------------------------------- registro de 303 presentados


def test_registrar_303_valida_aritmetica(svc390):
    with pytest.raises(ValueError, match=r"\[46\]"):
        svc390.registrar_303_presentado("2026-3T", {"07": "300", "09": "63", "27": "63", "46": "60", "71": "60"}, "I", J[3])
    with pytest.raises(ValueError, match="13 dígitos"):
        svc390.registrar_303_presentado("2026-3T", {"71": "0"}, "N", "123")
    with pytest.raises(ValueError, match="casilla 71"):
        svc390.registrar_303_presentado("2026-3T", {"07": "0"}, "N", J[3])


def test_registrar_303_con_justificante_pdf(svc390, tmp_path):
    casillas = {"07": "300,00", "09": "63,00", "27": "63,00", "46": "63,00", "71": "63,00"}
    pdf = pdf_justificante(tmp_path / "j.pdf", justificante=J[3], trimestre="3T", casillas=casillas)
    r = svc390.registrar_303_presentado("2026-3T", casillas, "U", J[3], "15-10-2026", str(pdf))
    a = r["autoliquidacion"]
    assert a["estado"] == "presentada" and a["fecha_presentacion"] == "2026-10-15"
    assert "fiscal-data" in a["justificante_pdf"]
    # Mismo justificante dos veces: no
    with pytest.raises(ValueError, match="ya está registrado"):
        svc390.registrar_303_presentado("2026-3T", casillas, "U", J[3])


def test_registrar_303_pdf_no_coincide(svc390, tmp_path):
    pdf = pdf_justificante(tmp_path / "j.pdf", justificante=J[3], trimestre="3T", casillas={"71": "63,00"})
    with pytest.raises(ValueError, match="no aparecen en el PDF"):
        svc390.registrar_303_presentado("2026-3T", {"07": "500", "09": "105", "27": "105", "46": "105", "71": "105"},
                                        "U", J[3], None, str(pdf))


def test_generado_pasa_a_presentado(svc390):
    """Lo generado por la herramienta y luego presentado queda como un único registro."""
    svc390.registrar_factura(factura_emitida(base="300.00", cuota="63.00", retencion="45.00", total="318.00"))
    svc390.confirmar_perfil("2026-3T", "test")
    assert svc390.generar_303("2026-3T")["generado"]
    [a] = svc390.listar_autoliquidaciones(2026, "303")["autoliquidaciones"]
    assert a["estado"] == "generada" and a["casillas"]["71"] == "63.00"
    r = svc390.registrar_303_presentado("2026-3T", {"07": "300", "09": "63", "27": "63", "46": "63",
                                                    "64": "63", "65": "100", "66": "63", "69": "63", "71": "63"},
                                        "U", J[3])
    assert "aviso" not in r
    [a] = svc390.listar_autoliquidaciones(2026, "303")["autoliquidaciones"]
    assert a["estado"] == "presentada" and a["justificante"] == J[3]


def test_presentado_distinto_de_generado_avisa(svc390):
    svc390.registrar_factura(factura_emitida(base="300.00", cuota="63.00", retencion="45.00", total="318.00"))
    svc390.confirmar_perfil("2026-3T", "test")
    assert svc390.generar_303("2026-3T")["generado"]
    r = svc390.registrar_303_presentado("2026-3T", {"71": "0"}, "N", J[3])
    assert "no coincide" in r["aviso"]


# ------------------------------------------------------------------- cálculo del 390


def test_390_sin_actividad_todo_el_ano(svc390):
    """Como 2026 real: 1T-3T presentados sin actividad y 4T generado sin actividad -> todo a cero."""
    for n in (1, 2, 3):
        sin_actividad(svc390, n)
    svc390.confirmar_perfil("2026-4T", "test")
    svc390.generar_303("2026-4T")
    r = svc390.calcular_390(2026)
    assert r["generable"], r["bloqueos"]
    assert r["resultado_liquidacion_anual"] == "0,00"
    assert any("no como presentado" in a for a in r["avisos"])


def test_390_anual_calculado_a_mano(svc390):
    """Ejercicio 2026 (cálculo a mano):
      3T: emitida 300,00 al 21 % -> 63,00. 303 presentado: [71] 63,00 (domiciliación).
      4T: emitida 1.000,00 al 21 % -> 210,00; recibida 100,00 al 21 % -> 21,00.
          303 generado: [46] = 210,00 − 21,00 = 189,00 = [71].
      1T y 2T: sin actividad.
    390:
      [05] = 300 + 1.000 = 1.300,00   [06] = 63,00 + 210,00 = 273,00
      [33] = 1.300,00  [34] = 273,00  [47] = [34] = 273,00
      [605] = 100,00   [606] = 21,00  [48] = 100,00  [49] = 21,00  [64] = 21,00
      [65] = 273,00 − 21,00 = 252,00 = [84] = [86] ([85] = 0)
      [95] = 63,00 + 189,00 = 252,00
      [99] = [108] = 1.300,00 (volumen: bases sin IVA)"""
    sin_actividad(svc390, 1)
    sin_actividad(svc390, 2)
    svc390.registrar_factura(factura_emitida(numero="3T-1", fecha="2026-08-10", base="300.00", cuota="63.00",
                                             retencion="45.00", total="318.00"))
    svc390.registrar_303_presentado("2026-3T", {"07": "300", "09": "63", "27": "63", "46": "63",
                                                "65": "100", "66": "63", "69": "63", "71": "63"}, "U", J[3])
    svc390.registrar_factura(factura_emitida(numero="4T-1", fecha="2026-10-05"))
    svc390.registrar_factura(factura_recibida(numero="P-4T", fecha="2026-10-07"))
    svc390.confirmar_perfil("2026-4T", "test")
    assert svc390.generar_303("2026-4T")["resultado"] == "189,00"
    r = svc390.calcular_390(2026)
    assert r["generable"], r["bloqueos"]
    assert {c: cas(r, "02", c) for c in ("05", "06", "33", "34")} == {
        "05": "1.300,00", "06": "273,00", "33": "1.300,00", "34": "273,00"}
    assert cas(r, "02B", "47") == "273,00"
    assert {c: cas(r, "03", c) for c in ("605", "606", "48", "49")} == {
        "605": "100,00", "606": "21,00", "48": "100,00", "49": "21,00"}
    assert (cas(r, "04", "64"), cas(r, "04", "65")) == ("21,00", "252,00")
    assert {c: cas(r, "06", c) for c in ("84", "85", "86", "95", "99", "108")} == {
        "84": "252,00", "85": "0,00", "86": "252,00", "95": "252,00", "99": "1.300,00", "108": "1.300,00"}


def test_390_4t_a_devolver(svc390):
    """4T solo con un gasto (100 al 21 %) y el usuario elige devolver: [71] = −21,00 -> [98] = 21,00."""
    for n in (1, 2, 3):
        sin_actividad(svc390, n)
    svc390.registrar_factura(factura_recibida(fecha="2026-10-07"))
    svc390.registrar_303_presentado("2026-4T", {"28": "100", "29": "21", "45": "21", "46": "-21", "71": "-21"}, "D", J[4])
    r = svc390.calcular_390(2026)
    assert r["generable"], r["bloqueos"]
    assert (cas(r, "06", "98"), cas(r, "06", "97"), cas(r, "04", "65")) == ("21,00", "0,00", "-21,00")


def test_390_falta_un_trimestre(svc390):
    sin_actividad(svc390, 1)
    r = svc390.calcular_390(2026)
    falta = [b for b in r["bloqueos"] if b.startswith("Falta el 303")]
    assert len(falta) == 3 and "Mis expedientes" in falta[0]


def test_390_trimestre_sin_alta(svc390):
    svc390.marcar_303_no_presentado("2026-1T", "Alta en la actividad en abril")
    for n in (2, 3, 4):
        sin_actividad(svc390, n)
    r = svc390.calcular_390(2026)
    assert r["generable"], r["bloqueos"]
    assert r["trimestres"][0]["estado"] == "no_presentada"


def test_390_libro_no_cuadra(svc390):
    """El 303 del 3T se presentó con 500 de base pero el libro solo tiene 300: no se genera."""
    for n in (1, 2, 4):
        sin_actividad(svc390, n)
    svc390.registrar_factura(factura_emitida(base="300.00", cuota="63.00", retencion="45.00", total="318.00"))
    svc390.registrar_303_presentado("2026-3T", {"07": "500", "09": "105", "27": "105", "46": "105", "71": "105"}, "I", J[3])
    r = svc390.calcular_390(2026)
    assert any("no cuadra" in b and "[07]" in b for b in r["bloqueos"])
    assert svc390.generar_390(2026)["generado"] is False


def test_390_662_no_soportado(svc390):
    sin_actividad(svc390, 1)
    svc390.registrar_factura(factura_recibida(fecha="2026-05-07"))
    svc390.registrar_303_presentado("2026-2T", {"28": "100", "29": "21", "45": "21", "46": "-21", "71": "-21"}, "C", J[2])
    for n in (3, 4):
        sin_actividad(svc390, n)
    r = svc390.calcular_390(2026)
    assert any("662" in b for b in r["bloqueos"])


def test_390_perfil(svc):
    """Sin los datos propios del 390 no se genera; exonerado, tampoco."""
    v = svc.ver_perfil("2026", "390")
    assert {p["campo"] for p in v["preguntas_pendientes"]} >= {"apellidos", "clave_actividad", "epigrafe_iae", "operaciones_347"}
    assert any("A05" in p.get("valores", "") for p in v["preguntas_pendientes"] if p["campo"] == "clave_actividad")
    with pytest.raises(ValueError, match="clave_actividad"):
        svc.actualizar_perfil({"clave_actividad": "Z99"})
    svc.actualizar_perfil({**PERFIL_390, "exonerado_390": True})
    svc.confirmar_perfil("2026-4T", "test")
    assert any("exonerado" in b for b in svc.calcular_390(2026)["bloqueos"])


# --------------------------------------------------------------- fichero del 390


def test_fichero_390_cumple_diseno(svc390):
    for n in (1, 2, 3):
        sin_actividad(svc390, n)
    svc390.registrar_factura(factura_recibida(fecha="2026-10-07"))
    svc390.registrar_303_presentado("2026-4T", {"28": "100", "29": "21", "45": "21", "46": "-21", "71": "-21"}, "C", J[4])
    g = svc390.generar_390(2026)
    assert g["generado"], g
    d = diseno.cargar(diseno.seleccionar(Trimestre(2026, 4), None, "390"))
    contenido = open(g["fichero"], "rb").read()
    texto = contenido.decode("iso-8859-1")
    assert "\n" not in texto
    assert texto.startswith("<T390020260A0000><AUX>") and texto.endswith("</T390020260A0000>")
    leido = fichero390.leer(d, contenido)
    assert set(leido) == set(fichero390.ESPEC.paginas)
    for cod, valores in leido.items():
        assert len(valores["__registro__"]) == d.paginas[cod].total
    p1 = leido["01"]
    assert (p1["nif"], p1["apellidos"].strip(), p1["nombre"].strip()) == ("12345678Z", "FICTICIO EJEMPLO", "AUTONOMO")
    assert (p1["clave_actividad"], p1["criterio_caja"], p1["operaciones_347"]) == ("A05", "2", "0")
    assert leido["03"]["[606]"] == "2100".zfill(17)
    assert leido["04"]["[65]"] == "N" + "2100".zfill(16)  # resultado negativo con signo
    assert leido["06"]["[97]"] == "2100".zfill(17)        # 4T a compensar
    assert leido["06"]["[84]#2"] == "0" * 17             # sección 8 (forales): vacía


def test_disenos_390_y_303_compatibles():
    from fiscal_es.core import fichero303

    for esp in (fichero303.ESPEC, fichero390.ESPEC):
        d = diseno.cargar(diseno.seleccionar(Trimestre(2026, 4), None, esp.modelo))
        assert d.modelo == esp.modelo
        assert fichero.compatibilidad(d, esp) == {"compatible": True, "problemas": []}


# ------------------------------------------------------- instrucciones del 390 (PDF)


def test_instrucciones_390_pdf(monkeypatch, tmp_path, svc):
    from conftest import generar_pdf

    pdf = generar_pdf(tmp_path / "i.pdf", [
        "9. Resultado de las liquidaciones.",
        "95 Total resultados a ingresar en las autoliquidaciones de IVA del ejercicio: se",
        "consignará la suma de las cantidades a ingresar.",
        "10. Volumen de operaciones.",
        "99 Operaciones en régimen general: se hará constar el importe total, excluido el IVA.",
    ]).read_bytes()
    g412 = '<a href="/static_files/Sede/Procedimiento_ayuda/G412/Instrucciones_modelo_390-2025.pdf">Instrucciones 2025</a>'

    def falso(url, cache, max_edad_s=0):
        return g412.encode() if url.endswith("G412.shtml") else pdf

    monkeypatch.setattr(instrucciones_aeat, "get_cacheado", falso)
    r = svc.consultar_instrucciones_390(2025, "casilla 95")
    assert r["resultados"][0]["texto"].startswith("95 Total resultados")
    assert r["resultados"][0]["seccion"].startswith("9. Resultado")
    with pytest.raises(LookupError, match="disponibles: 2025"):
        svc.consultar_instrucciones_390(2026, "casilla 95")
