"""Cálculo de casillas con resultados calculados a mano (documentados en cada test)."""

from conftest import factura_emitida, factura_recibida


def cas(r, pagina, casilla):
    return r["casillas"][pagina].get(casilla, "0,00")


def test_sin_actividad(svc):
    """Trimestre sin facturas (como 2026-1T/2T/3T reales): todo a cero, [65]=100,
    tipo de declaración N y marca de sin actividad."""
    r = svc.calcular_303("2026-3T")
    assert r["sin_actividad"] is True
    assert r["tipo_declaracion"] == "N"
    assert r["resultado"] == "0,00"
    assert r["casillas"] == {"01": {}, "03": {"65": "100,00"}}
    assert r["bloqueos"] == []


def test_una_emitida_21(svc):
    """Una emitida: base 300,00 al 21 %.
    Cuota = 300,00 × 0,21 = 63,00. Retención 15 % = 45,00. Total = 300 + 63 − 45 = 318,00.
    [07]=300,00 [09]=63,00 [27]=63,00 [45]=0 [46]=63,00 [64]=[66]=[69]=[71]=63,00 -> domiciliación (U)."""
    svc.registrar_factura(factura_emitida(base="300.00", cuota="63.00", retencion="45.00", total="318.00"))
    r = svc.calcular_303("2026-3T")
    assert (cas(r, "01", "07"), cas(r, "01", "09"), cas(r, "01", "27"), cas(r, "01", "46")) == ("300,00", "63,00", "63,00", "63,00")
    assert (cas(r, "03", "66"), cas(r, "03", "71")) == ("63,00", "63,00")
    assert r["tipo_declaracion"] == "U" and r["sin_actividad"] is False


def test_varias_emitidas_y_tipos(svc):
    """Emitidas:
      A: 1.000,00 al 21 % -> 210,00 (retención 150,00, total 1.060,00)
      B:   800,00 al 21 % -> 168,00 (retención 120,00, total   848,00)
      C: dos líneas: 200,00 al 10 % -> 20,00 y 50,00 al 4 % -> 2,00 (total 272,00)
    [01]=50,00 [03]=2,00 [04]=200,00 [06]=20,00 [07]=1.800,00 [09]=378,00
    [27]=2,00+20,00+378,00=400,00.
    Recibida: 100,00 al 21 % -> 21,00. [28]=100,00 [29]=21,00 [45]=21,00
    [46]=400,00−21,00=379,00 = [71]."""
    svc.registrar_factura(factura_emitida(numero="A"))
    svc.registrar_factura(factura_emitida(numero="B", base="800.00", cuota="168.00", retencion="120.00", total="848.00"))
    svc.registrar_factura(factura_emitida(
        numero="C", lineas=[{"base": "200", "tipo_iva": "10", "cuota": "20"}, {"base": "50", "tipo_iva": "4", "cuota": "2"}],
        retencion="0", total="272.00"))
    svc.registrar_factura(factura_recibida())
    r = svc.calcular_303("2026-3T")
    esperado_01 = {"01": "50,00", "03": "2,00", "04": "200,00", "06": "20,00", "07": "1.800,00", "09": "378,00",
                   "27": "400,00", "28": "100,00", "29": "21,00", "45": "21,00", "46": "379,00"}
    assert r["casillas"]["01"] == esperado_01
    assert cas(r, "03", "71") == "379,00"
    assert len(r["facturas_incluidas"]) == 4


def test_resultado_negativo_compensar(svc):
    """Solo gastos: recibida 100,00 al 21 % -> [29]=21,00, [46]=−21,00.
    Fuera del 4T: tipo C (a compensar)."""
    svc.registrar_factura(factura_recibida())
    r = svc.calcular_303("2026-3T")
    assert cas(r, "01", "46") == "-21,00" and cas(r, "03", "71") == "-21,00"
    assert r["tipo_declaracion"] == "C" and r["sin_actividad"] is False


def test_4t_negativo_requiere_decision(svc):
    """En el 4T el usuario elige compensar o devolver; sin decisión, bloqueo."""
    svc.actualizar_perfil({"exonerado_390": False})
    svc.confirmar_perfil("2026-4T", "test")
    svc.registrar_factura(factura_recibida(fecha="2026-10-05"))
    r = svc.calcular_303("2026-4T")
    assert any("compensar o devolver" in b for b in r["bloqueos"])
    r = svc.calcular_303("2026-4T", "devolver")
    assert r["tipo_declaracion"] == "D" and not any("compensar o devolver" in b for b in r["bloqueos"])


def test_cuotas_a_compensar(svc):
    """[110]=50,00 de periodos anteriores; resultado del periodo [66]=63,00.
    [78]=min(50,00; 63,00)=50,00 [87]=0 [69]=[71]=63,00−50,00=13,00."""
    svc.actualizar_perfil({"cuotas_a_compensar": "50"})
    svc.registrar_factura(factura_emitida(base="300.00", cuota="63.00", retencion="45.00", total="318.00"))
    r = svc.calcular_303("2026-3T")
    assert (cas(r, "03", "110"), cas(r, "03", "78"), cas(r, "03", "87"), cas(r, "03", "71")) == ("50,00", "50,00", "0,00", "13,00")


def test_cuotas_a_compensar_mayores_que_resultado(svc):
    """[110]=100,00, [66]=63,00 -> [78]=63,00 [87]=37,00 [71]=0 -> tipo N."""
    svc.actualizar_perfil({"cuotas_a_compensar": "100"})
    svc.registrar_factura(factura_emitida(base="300.00", cuota="63.00", retencion="45.00", total="318.00"))
    r = svc.calcular_303("2026-3T")
    assert (cas(r, "03", "78"), cas(r, "03", "87"), r["resultado"], r["tipo_declaracion"]) == ("63,00", "37,00", "0,00", "N")


def test_pendiente_bloquea(svc):
    svc.registrar_factura(factura_emitida(total="1"))
    r = svc.calcular_303("2026-3T")
    assert not r["generable"] and any("pendiente" in b for b in r["bloqueos"])
    g = svc.generar_303("2026-3T")
    assert g["generado"] is False
    g = svc.generar_303("2026-3T", ignorar_pendientes=True)
    assert g["generado"] is True and g["sin_actividad"] is True


def test_recibida_no_afecta_no_deduce(svc):
    svc.registrar_factura(factura_recibida(afecta_actividad=False))
    r = svc.calcular_303("2026-3T")
    assert cas(r, "01", "29") == "0,00" and r["avisos"]


def test_perfil_vacio_no_supone_nada(data_dir):
    """Sin entrevista, todo está sin confirmar y no se puede generar."""
    from fiscal_es.servicio import Servicio

    s = Servicio(data_dir)
    v = s.ver_perfil("2026-3T")
    campos = {p["campo"] for p in v["preguntas_pendientes"]}
    assert {"nif", "nombre", "regimen", "criterio_caja", "sii", "cuotas_a_compensar"} <= campos
    assert all(p["pregunta"] and p["donde"] for p in v["preguntas_pendientes"])
    assert "exonerado_390" not in campos  # solo en el 4T
    assert "exonerado_390" in {p["campo"] for p in s.ver_perfil("2026-4T")["preguntas_pendientes"]}
    r = s.calcular_303("2026-3T")
    assert not r["generable"] and any("sin confirmar" in b for b in r["bloqueos"])
    assert s.generar_303("2026-3T")["generado"] is False


def test_perfil_parcial_no_se_puede_confirmar(data_dir):
    import pytest

    from fiscal_es.servicio import Servicio

    s = Servicio(data_dir)
    s.actualizar_perfil({"nif": "12345678Z", "nombre": "X"})
    with pytest.raises(ValueError, match="faltan datos"):
        s.confirmar_perfil("2026-3T", "el usuario dice que sí")


def test_confirmacion_por_trimestre(svc):
    """Confirmado para 3T: el 1T de 2027 exige volver a confirmar."""
    assert svc.calcular_303("2026-3T")["generable"]
    r = svc.calcular_303("2027-1T")
    assert any("no ha confirmado" in b and "2026-3T" in b for b in r["bloqueos"])
    svc.confirmar_perfil("2027-1T", "el usuario confirma que no ha cambiado nada")
    assert svc.calcular_303("2027-1T")["generable"]


def test_confirmacion_no_por_actualizar(svc):
    import pytest

    with pytest.raises(ValueError, match="confirmar_perfil"):
        svc.actualizar_perfil({"confirmado_trimestre": "2027-1T"})


def test_situacion_no_soportada(svc):
    svc.actualizar_perfil({"criterio_caja": True})
    r = svc.calcular_303("2026-3T")
    assert any("criterio de caja" in b for b in r["bloqueos"])


def test_4t_exonerado_390(svc):
    svc.actualizar_perfil({"exonerado_390": True})
    svc.confirmar_perfil("2026-4T", "test")
    r = svc.calcular_303("2026-4T")
    assert any("página 4" in b for b in r["bloqueos"])


def test_ingreso_sin_forma_pago(svc):
    svc.actualizar_perfil({"forma_pago": None})
    svc.registrar_factura(factura_emitida())
    r = svc.calcular_303("2026-3T")
    assert any("forma de pago" in b for b in r["bloqueos"])

