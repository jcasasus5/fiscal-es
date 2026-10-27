"""Registro de facturas: validación, alcance, duplicados, verificación contra el PDF y trazabilidad.

Cubre los casos pedidos: normales (emitida y recibida), total mal, rectificativa,
ticket, duplicada, fuera de alcance y datos que no coinciden con el PDF.
"""

from conftest import NIF_CLIENTE, NIF_PROVEEDOR, NIF_YO, factura_emitida, factura_recibida, pdf_factura


def _pdf_emitida(tmp_path, nombre="f1.pdf", **kw):
    datos = dict(numero="2027-001", fecha="10/08/2026", emisor=("Autonomo Ficticio", NIF_YO),
                 receptor=("Cliente Ficticio SL", NIF_CLIENTE), base="1.000,00", tipo="21", cuota="210,00",
                 retencion="150,00", total="1.060,00")
    datos.update(kw)
    return pdf_factura(tmp_path / nombre, **datos)


def test_emitida_normal_con_pdf(svc, tmp_path):
    r = svc.registrar_factura(factura_emitida(), str(_pdf_emitida(tmp_path)), trimestre="2026-3T")
    assert r["resultado"] == "registrada", r
    f = r["factura"]
    assert f["verificacion_pdf"] == "ok"
    assert f["trimestre"] == "2026-3T"
    # El PDF se archiva dentro del directorio de datos
    assert "fiscal-data" in f["pdf"]


def test_recibida_normal(svc, tmp_path):
    pdf = pdf_factura(tmp_path / "p.pdf", numero="P-77", fecha="05/09/2026", emisor=("Proveedor Ficticio SA", NIF_PROVEEDOR),
                      receptor=("Autonomo Ficticio", NIF_YO), base="100,00", tipo="21", cuota="21,00", retencion=None,
                      total="121,00")
    r = svc.registrar_factura(factura_recibida(), str(pdf))
    assert r["resultado"] == "registrada", r


def test_total_mal(svc):
    r = svc.registrar_factura(factura_emitida(total="1210.00"))
    assert r["resultado"] == "pendiente"
    assert any(i["codigo"] == "total" and i["nivel"] == "error" for i in r["factura"]["incidencias"])


def test_cuota_mal(svc):
    r = svc.registrar_factura(factura_emitida(cuota="200.00", total="1050.00"))
    assert any(i["codigo"] == "cuota" for i in r["factura"]["incidencias"])


def test_rectificativa_fuera_de_alcance(svc):
    r = svc.registrar_factura(factura_emitida(numero="R-1", rectificativa=True))
    assert r["resultado"] == "pendiente"
    assert any(i["codigo"] == "rectificativa" and i["nivel"] == "fuera_alcance" for i in r["factura"]["incidencias"])


def test_ticket_recibido_fuera_de_alcance(svc):
    r = svc.registrar_factura(factura_recibida(numero="T-9", simplificada=True, nif_receptor=None))
    assert r["resultado"] == "pendiente"
    assert any(i["codigo"] == "simplificada" for i in r["factura"]["incidencias"])


def test_intracomunitaria_fuera_de_alcance(svc):
    r = svc.registrar_factura(factura_recibida(numero="EU-1", nif_emisor="FR40303265045", lineas=[{"base": "100", "tipo_iva": "0", "cuota": "0"}], total="100"))
    codigos = {i["codigo"] for i in r["factura"]["incidencias"]}
    assert {"emisor_extranjero", "tipo_iva"} <= codigos
    assert r["resultado"] == "pendiente"


def test_duplicada_por_numero_y_emisor(svc):
    assert svc.registrar_factura(factura_emitida())["resultado"] == "registrada"
    r = svc.registrar_factura(factura_emitida(numero="2027 001"))  # mismo número normalizado
    assert r["resultado"] == "duplicada"


def test_duplicada_por_pdf(svc, tmp_path):
    pdf = _pdf_emitida(tmp_path)
    assert svc.registrar_factura(factura_emitida(), str(pdf))["resultado"] == "registrada"
    r = svc.registrar_factura(factura_emitida(numero="OTRO"), str(pdf))
    assert r["resultado"] == "duplicada" and "PDF" in r["motivo"]


def test_datos_no_coinciden_con_pdf(svc, tmp_path):
    # El agente "lee" 2.000 € de base, pero el PDF dice 1.000 €.
    pdf = _pdf_emitida(tmp_path)
    r = svc.registrar_factura(factura_emitida(base="2000.00", cuota="420.00", retencion="300.00", total="2120.00"), str(pdf))
    assert r["resultado"] == "pendiente"
    inc = [i for i in r["factura"]["incidencias"] if i["codigo"] == "pdf_no_coincide"]
    assert inc and "2000" in inc[0]["mensaje"]


def test_emitida_que_no_es_mia(svc):
    r = svc.registrar_factura(factura_emitida(nif_emisor=NIF_PROVEEDOR))
    assert any(i["codigo"] == "no_eres_emisor" for i in r["factura"]["incidencias"])


def test_recibida_sin_confirmar_afectacion(svc):
    r = svc.registrar_factura(factura_recibida(afecta_actividad=None))
    assert r["resultado"] == "pendiente"
    fid = r["factura"]["id"]
    # 'revisar' se puede confirmar, pero mejor corregir el dato:
    r = svc.corregir_factura(fid, {"afecta_actividad": True}, "El usuario confirma que es material de oficina")
    assert r["factura"]["estado"] == "valida"


def test_confirmar_no_vale_para_errores(svc):
    fid = svc.registrar_factura(factura_emitida(total="9.99"))["factura"]["id"]
    import pytest

    with pytest.raises(ValueError):
        svc.confirmar_factura(fid, "me da igual")


def test_trazabilidad(svc):
    fid = svc.registrar_factura(factura_emitida(total="1000"))["factura"]["id"]
    svc.corregir_factura(fid, {"total": "1060.00"}, "Total mal leído: el PDF dice 1.060,00")
    svc.descartar_factura(fid, "Factura anulada")
    svc.reactivar_factura(fid, "Era válida")
    h = svc.historial_factura(fid)
    assert [e["accion"] for e in h["eventos"]] == ["alta", "correccion", "descarte", "reactivacion"]
    assert "1.060,00" in h["eventos"][1]["motivo"]
    assert h["factura"]["estado"] == "valida"


def test_otro_trimestre_avisa(svc):
    r = svc.registrar_factura(factura_emitida(fecha="2026-10-02"), trimestre="2026-3T")
    assert any(i["codigo"] == "otro_trimestre" for i in r["factura"]["incidencias"])
    assert r["factura"]["trimestre"] == "2026-4T"
