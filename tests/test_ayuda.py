"""Capacidades, consulta de instrucciones oficiales (sin red, con HTML simulado) e info de casillas."""

import pytest

from fiscal_es.core import aeat, alcance, instrucciones_aeat

BASE = "https://sede.agenciatributaria.gob.es/Sede/todas-gestiones/impuestos-tasas/iva/modelo-303-iva-autoliquidacion_/"

G414 = f"""<html><body>
<a href="/Sede/todas-gestiones/impuestos-tasas/iva/modelo-303-iva-autoliquidacion_/instrucciones-2026.html" class="stretched-link">Instrucciones 2026</a>
<a href="/Sede/todas-gestiones/impuestos-tasas/iva/modelo-303-iva-autoliquidacion_/instrucciones.html" class="stretched-link">Instrucciones 2024</a>
</body></html>"""

I2026_1T = """<html><body><nav><p>menú casilla 28</p></nav><main>
<h1>Instrucciones 2026</h1><h2>Instrucciones 01-1T de 2026</h2>
<a href="/Sede/todas-gestiones/impuestos-tasas/iva/modelo-303-iva-autoliquidacion_/instrucciones-2026/instrucciones-02-12-2t-4t-2026.html">Instrucciones 02 a 12 y 2T a 4T de 2026</a>
<h3>CUESTIONES GENERALES</h3>
<p>Texto del primer trimestre sobre la declaración sin actividad.</p>
</main></body></html>"""

I2026_RESTO = """<html><body><main>
<h1>Instrucciones 2026</h1><h2>Instrucciones 02 a 12 y 2T a 4T de 2026</h2>
<h3>CUESTIONES GENERALES</h3>
<p>Declaración “sin actividad"</p>
<p>La declaración será "sin actividad" cuando no se hayan devengado ni soportado cuotas durante el período declarado.</p>
<h4>IVA Deducible</h4>
<table><tr><td>28 a 39</td><td>Se harán constar las bases imponibles y el importe de las cuotas soportadas deducibles.</td></tr>
<tr><td>40 y 41</td><td>Rectificación de deducciones.</td></tr></table>
<h3>Información adicional</h3>
<p>110 Cuotas a compensar pendientes de períodos anteriores: se hará constar, con signo positivo, el importe.</p>
</main></body></html>"""

PAGINAS = {
    instrucciones_aeat.PAGINA_PROCEDIMIENTO: G414,
    BASE + "instrucciones-2026.html": I2026_1T,
    BASE + "instrucciones-2026/instrucciones-02-12-2t-4t-2026.html": I2026_RESTO,
}


@pytest.fixture
def sin_red(monkeypatch):
    def falso(url, cache, max_edad_s=0):
        return PAGINAS[url].encode()

    monkeypatch.setattr(instrucciones_aeat, "get_cacheado", falso)


def test_indice_por_ejercicio(sin_red):
    idx = instrucciones_aeat.indice_ejercicios(None)
    assert set(idx) == {2026, 2024}
    assert idx[2024].endswith("/instrucciones.html")


def test_paginas_y_extraccion(sin_red):
    pags = instrucciones_aeat.paginas_ejercicio(2026, None)
    assert [p.titulo for p in pags] == ["Instrucciones 01-1T de 2026", "Instrucciones 02 a 12 y 2T a 4T de 2026"]
    # Lo que está en <nav> no se indexa
    assert not any("menú" in b.texto for p in pags for b in p.bloques)


def test_buscar_casilla_en_tabla(sin_red):
    pags = instrucciones_aeat.paginas_ejercicio(2026, None)
    r = instrucciones_aeat.buscar(pags, "casilla 28", "3T")
    assert r and r[0]["texto"].startswith("28 a 39")
    assert "cuotas soportadas deducibles" in r[0]["texto"]
    assert r[0]["url"].endswith("instrucciones-02-12-2t-4t-2026.html")
    assert "IVA Deducible" in r[0]["seccion"]


def test_buscar_concepto_y_periodo(sin_red):
    pags = instrucciones_aeat.paginas_ejercicio(2026, None)
    r3 = instrucciones_aeat.buscar(pags, "sin actividad", "3T")
    assert all("2T a 4T" in x["pagina"] for x in r3)
    r1 = instrucciones_aeat.buscar(pags, "sin actividad", "1T")
    assert all("01-1T" in x["pagina"] for x in r1)


def test_sin_resultados_no_inventa(sin_red, svc):
    r = svc.consultar_instrucciones_303("2026-3T", "criptomonedas staking")
    assert r["resultados"] == [] and "No lo supongas" in r["nota"]


def test_servicio_indice_y_busqueda(sin_red, svc):
    idx = svc.consultar_instrucciones_303("2026-3T")
    assert idx["ejercicio"] == 2026 and idx["indice"][0]["secciones"]
    r = svc.consultar_instrucciones_303("2026-3T", "casilla 110 cuotas a compensar")
    assert "110 Cuotas a compensar" in r["resultados"][0]["texto"]


def test_ejercicio_no_publicado(sin_red, svc):
    with pytest.raises(LookupError, match="disponibles: 2024, 2026"):
        svc.consultar_instrucciones_303("2025-1T", "casilla 28")


def test_capacidades():
    c = alcance.capacidades()
    assert c["soportado"] and c["no_soportado"]
    assert "28" in c["casillas_calculadas"]["01"] and "71" in c["casillas_calculadas"]["03"]
    assert any(x["tema"] == "extranjero" for x in c["no_soportado"])


def test_info_casilla(svc):
    r = svc.info_casilla("28", "2026-3T")
    assert r["apariciones"][0]["la_calcula_la_herramienta"] is True
    r = svc.info_casilla("30", "2026-3T")  # bienes de inversión: no soportado
    assert r["apariciones"][0]["la_calcula_la_herramienta"] is False
    with pytest.raises(LookupError):
        svc.info_casilla("999", "2026-3T")


def test_solo_descarga_de_la_aeat():
    with pytest.raises(ValueError):
        aeat.get("https://ejemplo.com/x.html")
    with pytest.raises(ValueError):
        aeat.get("http://sede.agenciatributaria.gob.es/x.html")


def test_buscar_parrafo_que_empieza_por_casilla(sin_red):
    pags = instrucciones_aeat.paginas_ejercicio(2026, None)
    r = instrucciones_aeat.buscar(pags, "casilla 110", "3T", 1)
    assert "110 Cuotas a compensar" in r[0]["texto"]
