"""Integración del servidor MCP: listar tools y flujo completo hasta generar_303."""

import pytest
from fastmcp import Client

from conftest import PERFIL_COMPLETO, factura_emitida
from fiscal_es import mcp_server


@pytest.fixture
def servidor(data_dir):
    mcp_server._svc = None  # el Servicio se crea con FISCAL_DATA_DIR del test
    yield mcp_server.mcp
    if mcp_server._svc:
        mcp_server._svc.close()
    mcp_server._svc = None


async def test_lista_tools(servidor):
    async with Client(servidor) as c:
        nombres = {t.name for t in await c.list_tools()}
        assert {
            "plazos", "ver_perfil", "actualizar_perfil", "confirmar_perfil", "registrar_factura", "listar_facturas",
            "corregir_factura", "confirmar_factura", "descartar_factura", "comprobar_diseno_303",
            "instalar_diseno_303", "calcular_303", "generar_303",
            "capacidades", "consultar_instrucciones_303", "info_casilla",
            "registrar_303_presentado", "marcar_303_no_presentado", "listar_autoliquidaciones",
            "comprobar_diseno_390", "instalar_diseno_390", "consultar_instrucciones_390", "calcular_390", "generar_390",
        } <= nombres
        assert "buscar_facturas" not in nombres  # lo hace el agente con sus herramientas
        prompts = {p.name for p in await c.list_prompts()}
        assert "iva_trimestral" in prompts


async def test_flujo_completo(servidor, data_dir):
    async with Client(servidor) as c:
        r = await c.call_tool("generar_303", {"trimestre": "2026-3T"})
        assert r.data["generado"] is False  # sin perfil no se puede

        await c.call_tool("actualizar_perfil", {"cambios": PERFIL_COMPLETO, "motivo": "test"})
        r = await c.call_tool("calcular_303", {"trimestre": "2026-3T"})
        assert any("no ha confirmado" in b for b in r.data["bloqueos"])
        await c.call_tool("confirmar_perfil", {"trimestre": "2026-3T", "fuente": "el usuario lo confirma"})
        r = await c.call_tool("registrar_factura", {"datos": factura_emitida(), "trimestre": "2026-3T"})
        assert r.data["resultado"] == "registrada"

        r = await c.call_tool("calcular_303", {"trimestre": "2026-3T"})
        assert r.data["casillas"]["03"]["71"] == "210,00"

        r = await c.call_tool("generar_303", {"trimestre": "2026-3T"})
        assert r.data["generado"] is True
        assert r.data["fichero"].startswith(str(data_dir))
        assert r.data["fichero"].endswith(".303")
        assert r.data["siguientes_pasos"]


async def test_error_legible(servidor):
    async with Client(servidor) as c:
        r = await c.call_tool("calcular_303", {"trimestre": "2026-9T"}, raise_on_error=False)
        assert r.is_error
        assert "Trimestre no válido" in r.content[0].text
