# fiscal-es: tu gestoría del IVA trimestral dentro del agente

Le dices a tu agente (Claude Code, Codex, OpenClaw o cualquiera compatible con MCP):

> Hazme el 303 del primer trimestre.

El agente busca tus facturas, te pregunta lo que necesite saber, te explica el
resultado y te deja el **fichero oficial del modelo 303 listo para importar en la Sede
Electrónica de la AEAT**. Tú revisas, firmas y envías.

En enero hace lo mismo con el **modelo 390** (resumen anual del IVA), a partir de tus
facturas del año y de los 303 que presentaste.

> **Aviso.** Esta herramienta no sustituye tu revisión ni el asesoramiento fiscal
> profesional. Eres responsable de lo que presentas. Revisa siempre las casillas en la
> Sede antes de firmar.

## Cómo funciona

| Quién | Qué hace |
|---|---|
| **El agente** | Localiza las facturas con sus propias herramientas (carpetas, email…), las lee, te pregunta por tu situación fiscal y te explica el resultado. |
| **Las tools MCP (este repo)** | Todo lo determinista: validan cada factura (NIF, base × tipo = cuota, total con retención, alcance, duplicados, coincidencia con el PDF), llevan el libro registro con trazabilidad, calculan las casillas y generan el fichero. **Ningún importe lo calcula el LLM.** |
| **Tú** | Importas el fichero en la Sede, revisas, firmas y envías. La herramienta nunca presenta nada ni maneja certificados. |

El formato del fichero sale directamente del **Excel oficial de diseño de registro de
la AEAT** (`DR303eAAvNNN.xlsx`). Antes de cada declaración, el agente comprueba en la
web de la AEAT si se ha publicado uno nuevo y, si es compatible, lo instala.

## ¿Me sirve? Qué hace y qué no

> El agente puede consultarlo en cualquier momento con la tool `capacidades()`. Esa lista
> sale del mismo código que decide qué se acepta (`src/fiscal_es/core/alcance.py`).

### Te sirve si…

- Eres **autónomo o sociedad en régimen general del IVA**, presentas el 303
  **trimestralmente** y tributas en **territorio común** (no en País Vasco ni Navarra).
- Facturas a **clientes en España** al **21, 10 o 4 %**, con o sin retención de IRPF.
- Tus gastos con IVA son de **proveedores españoles**, con **factura completa a tu NIF**.

Con eso, el agente genera el 303 completo: IVA devengado por tipo, IVA deducible,
cuotas a compensar de trimestres anteriores, y el resultado a ingresar (ingreso o
domiciliación), a compensar, a devolver (en el 4T), cero o **sin actividad**.

### Desgravar (deducir el IVA de tus gastos)

**Sí, en los casos sencillos.** Si le das o le indicas tus facturas de gastos (también
puede buscarlas en tu email), el agente las registra y **te pregunta si cada gasto es de
tu actividad**; no lo decide él. La herramienta comprueba que la factura esté a tu NIF y
que las cuentas cuadren, y resta ese IVA (casillas 28/29). Así pagas menos, o el
resultado sale negativo y queda a compensar.

Solo se ocupa del **IVA del 303**. Los gastos deducibles en IRPF (modelo 130 o la renta)
son otra declaración.

### Lo que todavía NO hace

Si aparece alguno de estos casos, **no lo intenta cuadrar a medias**: la factura queda
pendiente con un aviso claro y el 303 no se genera hasta que la resuelvas (corregirla,
descartarla o hacerlo a mano o con un asesor).

| Caso | Ejemplos |
|---|---|
| Clientes o proveedores **extranjeros** | Suscripciones a Google Ads, Meta, AWS o Adobe facturadas desde Irlanda (inversión del sujeto pasivo), clientes de la UE, exportaciones, importaciones |
| Gastos que se deducen **solo en parte** | Coche, suministros de la vivienda |
| **Tickets** o facturas simplificadas como gasto | Gasolina, restaurantes con ticket |
| **Bienes de inversión** | Equipos de más de 3.005,06 € (casillas 30/31) |
| **Rectificativas** | Facturas rectificativas y abonos, autoliquidaciones rectificativas o complementarias |
| Otros **regímenes** | Módulos, recargo de equivalencia, criterio de caja, prorrata, SII, REDEME, foral, periodicidad mensual |
| Operaciones **exentas** | Formación reglada, sanidad, seguros… y tipos distintos de 21/10/4 % |
| **4T de exonerados del 390** | Página 4 del 303 del último trimestre |
| En el **390** | Autoliquidaciones complementarias o sustitutivas, cuotas a compensar generadas en el año y no aplicadas (casilla 662) |

## Resumen anual: modelo 390

Se presenta del 1 al 30 de enero, junto al 303 del 4T. Lo presentan todos los que hacen
el 303 salvo los exonerados: quienes solo tienen módulos o arrendamiento de locales
urbanos, y los del SII. **Un profesional en régimen general no está exonerado.**

| Dato del 390 | De dónde sale |
|---|---|
| IVA devengado y deducible por tipo, volumen de operaciones | Libro registro (las facturas del año) |
| Lo ingresado en el año [95], cuotas compensadas [85], resultado del 4T [97]/[98] | Los **303 presentados**, con su justificante |
| Apellidos y nombre, actividad, clave, epígrafe IAE, 347 | Perfil fiscal (tu último 390 o tu alta censal) |

**Los 303 presentados se registran.** Se guardan en el mismo libro local
(`libro.db`), junto con una copia del justificante PDF:
- **Los que genera la herramienta:** quedan como `generada`. Al presentarlos le pasas el
  justificante al agente y pasan a `presentada`.
- **Los que presentaste a mano antes de usar el plugin:** el agente te pide el
  justificante PDF (se descarga en la Sede, "Mi área personal" > "Mis expedientes"), lo
  lee y lo registra. La herramienta comprueba la aritmética entre casillas y que los
  datos aparecen en el PDF.

Antes de generar el 390, se **cruza cada trimestre del libro con su 303 presentado**.
Si no cuadran, no se genera y se explica la diferencia. La skill `resumen-anual-390` guía
todo el proceso. Las dudas se resuelven con `consultar_instrucciones_390`, que busca en
las instrucciones oficiales en PDF de la [ficha G412](https://sede.agenciatributaria.gob.es/Sede/procedimientoini/G412.shtml).

## Dudas: siempre con la información oficial

El agente no responde de memoria cómo se rellena el 303:

- `consultar_instrucciones_303(trimestre, consulta)` busca en las **instrucciones
  oficiales del modelo 303 que publica la AEAT para ese ejercicio**. Las encuentra desde
  la [ficha del procedimiento G414](https://sede.agenciatributaria.gob.es/Sede/procedimientoini/G414.shtml)
  (enlaces "Instrucciones AAAA") y devuelve el texto literal con su sección y su URL.
  Busca por casilla (`"casilla 28"`) o por concepto (`"sin actividad"`,
  `"cuotas a compensar"`).
- `info_casilla(casilla, trimestre)` dice qué es una casilla según el diseño de registro
  del periodo y si la herramienta la calcula.
- Si la respuesta no está en las instrucciones (por ejemplo, si un gasto concreto es
  deducible, que depende de la ley del IVA), el agente te lo dice en vez de inventarlo.

Desde la CLI: `fiscal instrucciones 2026-3T "casilla 28"` y `fiscal casilla 28 2026-3T`.

## Tools del servidor MCP

| Tool | Para qué |
|---|---|
| `capacidades` | Qué está soportado y qué no; qué casillas calcula |
| `plazos` | Próximos plazos de presentación y de domiciliación |
| `consultar_instrucciones_303`, `info_casilla` | Resolver dudas con las instrucciones oficiales del ejercicio y el diseño de registro (303 y 390) |
| `ver_perfil`, `actualizar_perfil`, `confirmar_perfil` | Tu situación fiscal: preguntas pendientes, datos y confirmación de cada trimestre |
| `registrar_factura`, `listar_facturas`, `corregir_factura`, `confirmar_factura`, `descartar_factura`, `reactivar_factura`, `historial_factura` | Libro registro con validación y trazabilidad |
| `comprobar_diseno_303`, `instalar_diseno_303` | Usar siempre el diseño de registro vigente de la AEAT |
| `calcular_303`, `generar_303` | Casillas con su explicación y el fichero `.303` |
| `registrar_303_presentado`, `marcar_303_no_presentado`, `listar_autoliquidaciones` | Registro de los 303 presentados (generados aquí o hechos a mano), con su justificante |
| `comprobar_diseno_390`, `instalar_diseno_390`, `consultar_instrucciones_390` | Diseño de registro e instrucciones oficiales del 390 |
| `calcular_390`, `generar_390` | Resumen anual cruzado con los 303 y el fichero `.390` |

La búsqueda de facturas no es una tool: la hace el agente con sus propias herramientas
(carpetas, email…) y pasa los datos a `registrar_factura`.

## Instalación

Requisitos: [uv](https://docs.astral.sh/uv/) (`uvx` en el PATH).

### Claude Code (plugin + marketplace)

```
/plugin marketplace add jcasasus5/fiscal-es
/plugin install fiscal-es@fiscal-es
```

El plugin trae el servidor MCP (`fiscal`) y la skill `iva-trimestral`
(`/fiscal-es:iva-trimestral`). Para no tener que aprobar cada llamada, puedes añadir
en tu `settings.json`:

```json
{ "permissions": { "allow": ["mcp__plugin_fiscal-es_fiscal__*"] } }
```

### Codex (plugin + marketplace)

El repo es también un marketplace de Codex (`.agents/plugins/marketplace.json`). El plugin
usa el formato portable [Agent Plugins](https://agent-plugins.org): `plugin.json`,
`mcp.json` y `skills/` en la raíz del plugin.

```bash
codex plugin marketplace add jcasasus5/fiscal-es
codex plugin add fiscal-es@fiscal-es
```

También se puede instalar desde `/plugins` dentro de Codex. Así se instalan el servidor
MCP `fiscal` y la skill `iva-trimestral`. Los datos van a `~/fiscal-data`; para usar
otra carpeta, define `FISCAL_DATA_DIR` en tu entorno.

**Alternativa manual** (sin plugin), en `~/.codex/config.toml`:

```toml
[mcp_servers.fiscal]
command = "uvx"
args = ["--from", "git+https://github.com/jcasasus5/fiscal-es@v0.4.1", "fiscal-mcp"]

[mcp_servers.fiscal.env]
FISCAL_DATA_DIR = "/home/tu-usuario/fiscal-data"
```

En ese caso, copia `plugins/fiscal-es/skills/iva-trimestral/` a `~/.agents/skills/`.
Aunque no la copies, el servidor MCP envía las mismas instrucciones del flujo en su
campo `instructions` y como prompt `iva_trimestral`.

### OpenClaw

OpenClaw reconoce la carpeta `plugins/fiscal-es/` como bundle compatible: carga la skill
y el servidor de `.mcp.json`. Con el repo clonado:

```bash
openclaw plugins install ./fiscal-es/plugins/fiscal-es
openclaw gateway restart
```

**Alternativa manual**, en `~/.openclaw/openclaw.json`:

```json5
{
  mcp: {
    servers: {
      fiscal: {
        command: "uvx",
        args: ["--from", "git+https://github.com/jcasasus5/fiscal-es@v0.4.1", "fiscal-mcp"],
        env: { FISCAL_DATA_DIR: "/home/tu-usuario/fiscal-data" },
      },
    },
  },
}
```

La skill va en `~/.agents/skills/iva-trimestral/` (o en `~/.openclaw/skills/`).

### CLI, sin agente

```bash
uv tool install git+https://github.com/jcasasus5/fiscal-es@v0.4.1
fiscal plazos
fiscal perfil ver 2027-1T            # preguntas pendientes y dónde mirar cada dato
fiscal perfil set '{"nif": "...", "nombre": "APELLIDOS NOMBRE", "regimen": "general", ...}' --motivo "último 303"
fiscal perfil confirmar 2027-1T --fuente "sigue todo igual"
fiscal factura registrar factura.json --pdf factura.pdf
fiscal diseno comprobar 2027-1T
fiscal generar-303 2027-1T
```

Para el resumen anual:

```bash
fiscal autoliquidacion registrar-303 2026-1T '{"65": 100, "71": 0}' --tipo N --justificante 3030000000000 --pdf justificante.pdf
fiscal autoliquidacion listar 2026
fiscal calcular-390 2026
fiscal generar-390 2026
```

`fiscal --help` muestra todos los comandos.

## Un trimestre de principio a fin

```
Tú:      Hazme el 303 del primer trimestre.
Agente:  (plazos) Es el 2027-1T; tienes hasta el 20 de abril (domiciliando, hasta el 15).
         (comprobar_diseno_303) El diseño de registro de la AEAT sigue siendo el de 2026: al día.
         (ver_perfil) Tengo tu perfil: domiciliación en tu cuenta ES…1332 y sin cuotas a compensar. ¿Sigue igual?
Tú:      Sí. Las facturas están en ~/Documentos/facturas/2027.
Agente:  He encontrado 2 facturas emitidas y 1 ticket de gasolina.
         (registrar_factura ×3) Las dos emitidas cuadran. El ticket queda pendiente: los
         tickets como gasto deducible aún no están soportados. ¿Lo dejo fuera?
Tú:      Sí, quítalo. Y busca en mi email, que creo que hice otra en marzo.
Agente:  (descartar_factura, busca en el email, registrar_factura) Encontrada la F-2027-003 del 28/03.
         (calcular_303) Resultado: 346,50 € a ingresar por domiciliación.
           [07] base al 21 %: 1.650,00 €   [09] cuota: 346,50 €  (F-2027-001, 002 y 003)
         (generar_303) Fichero: ~/fiscal-data/303/2027-1T/…_303_2027_1T.303
```

## Tu perfil fiscal: nada se supone

Para rellenar la identificación del 303, la herramienta necesita conocer tu situación:
régimen, periodicidad, territorio, criterio de caja, SII, REDEME, prorrata, concurso,
forma de pago, IBAN, cuotas a compensar y, en el 4T, si estás exonerado del 390.

- **Todo empieza sin confirmar.** Mientras falte algún dato, el 303 no se genera.
  `ver_perfil` devuelve cada pregunta pendiente con dónde mirar la respuesta.
- **La mejor fuente es tu último 303 presentado** (el justificante PDF): muestra las
  casillas que aceptó la AEAT, la forma de pago y las cuotas a compensar. Después, tus
  datos censales en la Sede o tu 036/037. Si no se sabe un dato, no se supone.
- **Cada trimestre hay que confirmar el perfil** (`confirmar_perfil`) antes de generar,
  sobre todo las cuotas a compensar, que cambian de un trimestre a otro.

## Importar y presentar en la Sede

1. Entra en la Sede de la AEAT → IVA → Modelo 303 → Presentar (certificado, Cl@ve o DNIe).
2. Elige la opción de importar un fichero y selecciona el `.303` generado.
3. Revisa todas las casillas. Los datos importados no se editan en la Sede: si algo
   no está bien, corrígelo con el agente y vuelve a generar e importar el fichero.
4. Valida, y después **Firmar y enviar**.
5. Guarda el justificante (PDF con CSV).

## Diseño de registro: comprobación y ejercicios nuevos

Funciona igual para el 303 y para el 390. El lector identifica el modelo y las páginas
por el propio contenido del Excel oficial, no por el nombre del fichero.

- Los Excel oficiales se guardan en `src/fiscal_es/disenos/` con un `manifest.json`
  que indica desde qué trimestre aplica cada uno. Hace falta guardarlos porque la AEAT
  solo publica el vigente.
- `comprobar_diseno_303` (o `fiscal diseno comprobar <trimestre>`) consulta
  https://sede.agenciatributaria.gob.es/Sede/ayuda/disenos-registro/modelos-300-399.html,
  descarga el Excel aplicable y compara su hash y su contenido con el instalado.
- `instalar_diseno_303` lo guarda en `FISCAL_DATA_DIR/disenos/` y comprueba si la
  herramienta sabe rellenarlo: todos los campos se identifican por su número de casilla
  o por su descripción. Si aparece un campo desconocido o desaparece uno necesario,
  avisa y **no se genera el fichero** hasta actualizar el código.
- **Añadir un ejercicio a mano:** copia el `.xlsx` oficial en `src/fiscal_es/disenos/`
  y añade su entrada al `manifest.json` (`modelo`, `archivo`, `desde`, `actualizado`,
  `sha256`, `fuente`). También vale `fiscal diseno instalar --xlsx ruta.xlsx --desde 2027-1T`.
  No hay posiciones escritas a mano en el código.

## Tus datos

- Todo vive en `FISCAL_DATA_DIR` (por defecto `~/fiscal-data/`), fuera del repo:
  - `libro.db`: libro registro con su historial de cambios.
  - `perfil.json`: tu NIF, nombre e IBAN (permisos 600).
  - `facturas/`: copia de los PDFs.
  - `303/` y `390/`: ficheros generados con su resumen.
  - `autoliquidaciones/`: copia de los justificantes de los 303 presentados.
  - `disenos/`: diseños descargados.
  - `cache_aeat/`: copia temporal de las páginas de instrucciones de la AEAT.
- Las tools no envían datos a ningún sitio. Las únicas conexiones son de solo lectura a
  `sede.agenciatributaria.gob.es`, para descargar el diseño de registro y las
  instrucciones públicas.
- **Ojo:** el agente (y por tanto el proveedor del modelo: Anthropic, OpenAI…) **sí ve**
  las facturas que lee y lo que devuelven las tools. Los cálculos, la base de datos y
  los ficheros se quedan en tu equipo.
- Nada se borra del libro: cada alta, corrección, confirmación o descarte queda
  registrado con su motivo (`historial_factura`).

## Desarrollo

```bash
uv sync
uv run pytest
claude plugin validate ./ && claude plugin validate ./plugins/fiscal-es
```

Estructura:
- `src/fiscal_es/core/`: lógica fiscal pura.
- `servicio.py`: casos de uso.
- `mcp_server.py`: FastMCP sobre stdio.
- `cli.py`: Typer.
- `plugins/fiscal-es/`: el plugin, con dos manifiestos: `.claude-plugin/` y `.mcp.json`
  para Claude Code, y `plugin.json` y `mcp.json` (formato Agent Plugins) para Codex.
- `.claude-plugin/marketplace.json` (Claude Code) y `.agents/plugins/marketplace.json` (Codex).

Los tests generan facturas PDF sintéticas con datos ficticios. En el repo no hay PDFs
ni datos reales.

## Licencia

MIT.
