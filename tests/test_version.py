"""La versión debe coincidir en el paquete, los manifiestos de ambos agentes y la URL del MCP."""

import json
import re
import tomllib
from pathlib import Path

import fiscal_es

RAIZ = Path(__file__).resolve().parent.parent
PLUGIN = RAIZ / "plugins" / "fiscal-es"


def test_versiones_coherentes():
    v = tomllib.loads((RAIZ / "pyproject.toml").read_text())["project"]["version"]
    assert fiscal_es.__version__ == v
    assert json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"] == v
    assert json.loads((PLUGIN / "plugin.json").read_text())["version"] == v
    for mcp in (".mcp.json", "mcp.json"):
        args = json.loads((PLUGIN / mcp).read_text())["mcpServers"]["fiscal"]["args"]
        assert any(a.endswith(f"@v{v}") for a in args), (mcp, args)
    # Los ejemplos del README apuntan a la misma versión
    assert set(re.findall(r"@v(\d+\.\d+\.\d+)", (RAIZ / "README.md").read_text())) == {v}
