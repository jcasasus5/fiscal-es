# Proyecto: fiscal-es, tu gestoría del IVA dentro del agente (modelo 303)

> Versión 2 (2026-10-24). Sustituye al prompt inicial. Incorpora la investigación
> sobre el diseño de registro del 303 y el enfoque conversacional.

## Objetivo
Soy autónomo en España y presento yo mismo el IVA trimestral (modelo 303) en la Sede
Electrónica de la AEAT. Quiero que mi agente (Claude Code, Codex, OpenClaw o cualquier
agente compatible con MCP) haga el trabajo que haría una gestoría. En lugar de enviarle
a una empresa externa cada factura que emito y que ellos lleven el trámite, le digo a
mi agente:

> "Genérame el 303 del primer trimestre."

El agente:
- se encarga de todo el proceso;
- me pregunta lo que necesite saber de mi situación;
- me explica lo que ha hecho;
- me deja el fichero oficial listo para **importar en la Sede, revisar, firmar y enviar
  yo**.

Después de generarlo, tengo que poder seguir hablando con él:
- "se te ha pasado una factura, está en esta otra carpeta";
- "busca en mi email las facturas de este trimestre";
- "esta factura es de otro trimestre, quítala";
- "¿por qué sale este importe en la casilla 09?".

El caso principal es sencillo: pocas facturas emitidas, casi todas al 21 %, y
trimestres sin actividad (el 303 sale "sin actividad" con resultado 0). Los dos casos
principales son **"sin actividad"** y **"unas pocas facturas emitidas al 21 %"**, y tienen
que funcionar perfectamente.

## Reparto de responsabilidades: agente frente a tools
**El agente hace de gestor**, usando las capacidades que ya tiene (leer ficheros,
buscar en carpetas, conectores de email, navegación web…):
- Localiza las facturas donde yo le diga (carpetas, email, adjuntos) y extrae sus datos.
  **No hace falta una tool `buscar_facturas`**: eso lo resuelve el agente con sus
  herramientas.
- Me hace las preguntas necesarias para conocer mi situación fiscal y rellenar bien el
  formulario. Por ejemplo:
  - qué casillas de identificación marcar;
  - si tengo cuotas a compensar de periodos anteriores;
  - si estoy exonerado del 390;
  - cómo quiero pagar;
  - si el volumen anual de operaciones es distinto de cero (último periodo).
- Me explica el resultado y me guía en la presentación.
- Si tiene una duda fiscal que afecte a un cálculo, **me pregunta en vez de asumir**.

**Las tools MCP hacen todo lo determinista**: validar, guardar, calcular y generar el
fichero. **Ningún importe ni casilla lo calcula el LLM.** El agente solo aporta los datos
de entrada (los de cada factura y las respuestas del perfil), y las tools los validan.

### Datos censales
El agente **no puede consultar mis datos censales en la AEAT**: eso exige certificado o
Cl@ve, y la herramienta no maneja credenciales. Las alternativas son:
- preguntarme;
- o pedirme que descargue el certificado de situación censal o una captura de "Mis
  datos censales" y leerlo.

Con eso se construye un **perfil fiscal** persistente: régimen, periodicidad, epígrafe,
criterio de caja, SII, prorrata, exoneración del 390, forma de pago e IBAN. En cada
trimestre el agente me confirma que nada ha cambiado, en vez de volver a preguntarlo
todo.

## Arquitectura (obligatoria)
Un único repo con tres capas:

1. **Core** (`src/fiscal_es/core/`): librería Python pura con toda la lógica fiscal.
   - **Libro registro en SQLite** como fuente de verdad. Deduplica por hash del PDF y
     por número de factura + NIF del emisor. Lleva trazabilidad: cada alta, corrección o
     descarte queda registrado con su motivo y no se borra nada.
   - **Validación determinista de facturas:**
     - base × tipo = cuota (con tolerancia de redondeo definida);
     - total = base + cuota − retención de IRPF (mis emitidas llevan retención);
     - dígitos de control de NIF/CIF/NIE;
     - fecha dentro del periodo.
   - **Verificación cruzada contra el PDF.** Si el PDF tiene capa de texto, se comprueba
     que el número de factura, el NIF, la base, la cuota y el total que aporta el agente
     aparecen en él. Así se detectan lecturas erróneas o inventadas. Si no se puede
     comprobar (por ejemplo, un escaneado), se avisa.
   - **Perfil fiscal** persistente, en un fichero dentro del directorio de datos.
   - **Cálculo determinista de las casillas del 303** a partir del libro registro y del
     perfil.
   - **Generación del fichero importable del 303** según el diseño de registro del
     ejercicio correspondiente.
   - (Opcional) Exportar el libro registro en el formato Excel del Pre303 de la AEAT,
     como plan B o para cotejar el resultado.
2. **Servidor MCP** (`src/fiscal_es/mcp_server.py`): capa fina con FastMCP sobre stdio.
3. **CLI** (`src/fiscal_es/cli.py`): los mismos comandos sin agente (por ejemplo
   `fiscal generar-303 2027-1T`), con Typer o Click.

Entry points en `pyproject.toml`: `fiscal-mcp` y `fiscal`. Gestión con `uv`.

## Tools MCP
Las descripciones deben dejar claro a cualquier LLM cuándo usar cada una y qué no debe
hacer él mismo (calcular importes).

- `ver_perfil()` / `actualizar_perfil(cambios)`: perfil fiscal. Devuelve también los
  datos que faltan para poder rellenar el 303.
- `registrar_factura(datos, ruta_pdf?)`: el agente aporta los datos extraídos (de un PDF,
  un email…). La tool valida, deduplica y guarda.
  - Si algo no cuadra o está fuera de alcance, la factura queda **pendiente de
    revisión**, con el motivo, y no entra en los cálculos.
- `listar_facturas(trimestre, estado?)`
- `corregir_factura(id, cambios, motivo)` / `descartar_factura(id, motivo)`: siempre con
  trazabilidad.
- `comprobar_diseno_303(ejercicio, periodo)`: ver la sección siguiente.
- `instalar_diseno_303(origen)`: ver la sección siguiente.
- `calcular_303(trimestre)`: devuelve:
  - las casillas en formato legible;
  - una explicación de dónde sale cada importe (qué facturas);
  - los avisos: pendientes sin resolver, datos de perfil que faltan, diseño de registro
    no verificado…
- `generar_303(trimestre)`: escribe el fichero importable y devuelve la ruta y un resumen.
  - **Se niega a generar el fichero** si hay pendientes sin resolver o falta un dato
    obligatorio del perfil, salvo con `forzar=true` explícito.
- `plazos()`: próximos vencimientos del 303, con el ajuste por festivos y fines de semana
  y el plazo de domiciliación.

Además de las tools, el servidor MCP expone las **instrucciones del flujo** (campo
`instructions` del servidor y/o un *prompt* MCP). Así, los agentes que no cargan skills
de Claude Code también sepan comportarse como gestor.

## Diseño de registro del 303: siempre la plantilla vigente
### Lo que ya está verificado (2026-10-24)
- No hay una "plantilla PDF" que rellenar. El PDF que da la Sede es el **justificante**
  de la presentación.
- Lo que se importa en el formulario web del 303 es un **fichero de texto de ancho fijo**
  (formato BOE) que sigue el **diseño de registro** publicado por la AEAT.
  - Los datos importados no se pueden editar en la Sede: si algo está mal, se corrige el
    fichero y se vuelve a importar.
- Los diseños están en
  https://sede.agenciatributaria.gob.es/Sede/ayuda/disenos-registro/modelos-300-399.html.
  - El vigente es `DR303e26v101.xlsx`: "Ejercicio 2026 y siguientes", actualizado el
    28/01/26.
  - Es un Excel legible por máquina: una hoja por página del modelo (`DP30300` cabecera,
    `DP30301`…`DP30305`, `DP303DID` domiciliación/devolución), con número de campo,
    posición, longitud, tipo, descripción, casilla y validación.
  - Los importes van en 17 posiciones: 15 enteros y 2 decimales.
- **El diseño no cambia cada trimestre, pero sí casi cada año** (2024, 2025 y 2026 han
  tenido versión nueva). También puede cambiar a mitad de ejercicio: la Orden
  HAC/27/2026 modificó el 303 a partir del 2T 2026.
- La web de la AEAT **solo publica el diseño vigente**. Los anteriores desaparecen, así
  que hay que guardar en el repo una copia de cada versión.
- Alternativa oficial: el **Pre303** importa el libro registro en el Excel de la AEAT y
  la propia AEAT calcula las casillas.

### Requisito: el agente siempre comprueba si hay diseño nuevo
Antes de cada declaración, el flujo (skill + instrucciones del MCP) obliga a:

1. Llamar a `comprobar_diseno_303(ejercicio, periodo)`. La tool:
   - consulta la página oficial de diseños de registro (solo `sede.agenciatributaria.gob.es`;
     es información pública y no se envía ningún dato fiscal);
   - identifica qué diseño corresponde al ejercicio y periodo de la declaración;
   - lo compara con los que tiene instalados (nombre, versión, fecha de actualización y
     hash del fichero).
2. Si hay uno nuevo, llamar a `instalar_diseno_303(origen)`. La tool:
   - descarga el Excel oficial y lo convierte en la especificación versionada;
   - lo guarda en el directorio de datos (`disenos/`), no dentro del paquete instalado
     (que con `uvx` es de solo lectura);
   - muestra un diff frente a la versión anterior: campos añadidos, eliminados o movidos,
     y casillas nuevas.
3. Si los cambios solo mueven posiciones o añaden campos que no uso, el agente sigue con
   el diseño nuevo.
   - Si afectan a casillas que la herramienta rellena, o hay validaciones que no sabe
     aplicar, el agente **para, me explica el cambio y no genera el fichero** hasta
     resolverlo (puede requerir una versión nueva del código).
4. Si no hay conexión, el agente avisa de que no ha podido comprobarlo y me pregunta si
   seguir con el diseño instalado.

Además, el repo incluye los diseños oficiales conocidos (empezando por
`DR303e26v101.xlsx`). La especificación se genera **siempre a partir del Excel oficial**:
no se inventan posiciones ni números de casilla. Añadir un ejercicio nuevo debe consistir
solo en añadir su Excel.

## Flujo trimestral (lo que describe la skill)
La skill `iva-trimestral` (y las instrucciones del servidor MCP) guían al agente así:

1. **Determinar el periodo y el plazo.** Si le digo "el del primer trimestre", deduce el
   ejercicio y me recuerda la fecha límite (y la de domiciliación).
2. **Comprobar el diseño de registro** (sección anterior).
3. **Revisar el perfil fiscal.**
   - La primera vez, me entrevista (o lee mi certificado censal).
   - Las siguientes veces, me confirma que nada ha cambiado.
   - En el último periodo (4T) pregunta además lo que solo se rellena entonces.
4. **Recopilar facturas** con sus propias herramientas: las carpetas que le indique, el
   email si tiene un conector… Me pregunta si hay más fuentes o si falta alguna factura.
5. **Registrar cada factura** con `registrar_factura` y resolverme las incidencias una a
   una.
6. **Calcular** con `calcular_303` y **explicarme** el resultado en lenguaje claro.
   - Si no hay ninguna factura, me confirma que sale "sin actividad".
7. **Generar** el fichero con `generar_303` y decirme dónde está.
8. **Guiarme en la Sede:** entrar en el formulario del 303, importar el fichero, revisar,
   validar, firmar y enviar, y guardar el justificante.
9. Quedar disponible para correcciones: si añado o quito algo, vuelve al paso 5 y
   regenera.

Reglas de la skill:
- No calcular importes por su cuenta.
- No presentar nada.
- Preguntar ante cualquier duda fiscal.
- No dar por buena una factura que no cuadra.

## Restricciones de seguridad (no negociables)
- Todo se ejecuta en local. Sin servidor HTTP propio, sin telemetría y sin enviar datos
  fiscales a servicios externos desde las tools.
  - Única excepción: `comprobar_diseno_303` / `instalar_diseno_303` descargan
    información pública de `sede.agenciatributaria.gob.es`.
- **Hay que asumirlo y documentarlo en el README:** al ser un flujo conversacional, el
  agente (y por tanto el proveedor del modelo) ve los datos de las facturas que lee y lo
  que devuelven las tools. Los cálculos, el SQLite y los ficheros se quedan en local.
- **Nunca presentar nada ante la AEAT.** No implementar envío ni firma, ni manejar
  certificados o credenciales. El último paso lo hago yo en la Sede.
- Los datos (facturas, SQLite, perfil, diseños descargados, ficheros generados) viven
  fuera del repo, en una ruta configurable (por defecto `~/fiscal-data/`, con variable de
  entorno `FISCAL_DATA_DIR`).
  - El IBAN y el NIF solo se guardan ahí.
  - Patrones defensivos en `.gitignore`: `*.pdf`, `*.db`, `*.303`, `fiscal-data/`. Con
    una excepción para las fixtures de tests, o mejor, generando las fixtures al
    ejecutar los tests.
- El libro registro no se modifica sin trazabilidad.
- El repo no debe contener datos personales reales (NIF, nombre, IBAN, importes de mis
  declaraciones).

## Alcance fiscal inicial
Régimen general, operaciones interiores, tipos 21/10/4 %, sin prorrata, sin recargo de
equivalencia, sin inversión del sujeto pasivo, sin operaciones intracomunitarias,
criterio de devengo y periodicidad trimestral.

Prioridad:
1. "Sin actividad".
2. Facturas emitidas al 21 % con retención de IRPF.
3. Facturas recibidas con IVA deducible (casillas 28/29).

Lo que caiga fuera de este alcance queda pendiente, con un aviso claro, en vez de
intentar tratarlo.

Dudas fiscales que **hay que preguntarme antes de implementar** su cálculo:
- tickets o facturas simplificadas como gasto deducible;
- rectificativas (periodo y signo);
- bienes de inversión frente a corrientes;
- gastos de uso mixto;
- cuotas a compensar y la opción compensar/devolver en el 4T.

El 390 queda fuera de la primera versión. Si en el 4T hace falta, el agente me lo dirá y
lo veremos aparte.

## Distribución como plugin y marketplace
El mismo repo debe funcionar como marketplace de plugins de Claude Code:

```
fiscal-es/
├── src/fiscal_es/
│   └── disenos/              # Excel oficiales del 303 por ejercicio/versión
├── tests/
├── pyproject.toml
├── .claude-plugin/marketplace.json
└── plugins/fiscal-es/
    ├── .claude-plugin/plugin.json
    ├── .mcp.json
    └── skills/iva-trimestral/SKILL.md
```

- `.mcp.json` lanza el servidor con
  `uvx --from git+https://github.com/<usuario>/fiscal-es@<tag> fiscal-mcp`.
  - Va **fijado a un tag**, no a `main`: es una herramienta fiscal y no debe actualizarse
    sola.
- Hay que verificar en la documentación actual de Claude Code el formato exacto de
  `marketplace.json`, `plugin.json`, `.mcp.json` y `SKILL.md` en plugins. No hay que
  suponerlo.
- Hay que verificar también cómo se cargan skills o instrucciones en Codex y OpenClaw.
  Donde no haya skills, el flujo debe llegar por las instrucciones del servidor MCP.

## Tests
- **Fixtures sintéticas** (datos ficticios, generadas en los tests):
  - un trimestre sin facturas ("sin actividad");
  - emitidas al 21 % con retención;
  - una con el total mal;
  - una rectificativa;
  - un ticket;
  - una duplicada;
  - una fuera de alcance;
  - una en la que los datos del agente no coinciden con el texto del PDF.
- **Tests unitarios del cálculo de casillas**, con los resultados calculados a mano y
  documentados en el propio test.
- **Test del fichero generado frente al diseño de registro**, leyendo la especificación
  desde el Excel oficial: longitudes, tipos, relleno, importes y codificación.
- **Test de `instalar_diseno_303`** con un Excel modificado: tiene que detectar y
  explicar las diferencias.
- **Test de integración del servidor MCP:** listar las tools y hacer el flujo completo
  (registrar → calcular → generar).

## Documentación
README en español con:
- Instalación en Claude Code (marketplace), Codex (`~/.codex/config.toml`), OpenClaw y
  uso por CLI.
- Ejemplo de conversación de un trimestre completo.
- Cómo importar el fichero en la Sede, validar, firmar y enviar.
- Cómo funciona la comprobación y actualización del diseño de registro.
- Qué datos ve el proveedor del modelo y cuáles se quedan en local.
- Aviso claro: la herramienta no sustituye la revisión del contribuyente ni el
  asesoramiento fiscal.

## Forma de trabajar
1. **Primero, un informe de investigación**, y esperar mi visto bueno. Debe cubrir:
   - `arrendatools-modelo303` (PyPI): genera el 303 desde el Excel de la AEAT. ¿Usarla
     como dependencia o como referencia? ¿Qué licencia tiene?
   - `facturas-inbox-mcp` (GitHub, pedrozapatadev): referencia para validar facturas
     españolas. Revisar la licencia.
   - Detalle del diseño `DR303e26v101.xlsx`: campos obligatorios en el caso "sin
     actividad" y en el caso con facturas; codificación; extensión del fichero.
   - Formato de plugins y skills en Claude Code, Codex y OpenClaw.
2. **Después, un plan por fases** con hitos verificables:
   - core y tests;
   - CLI;
   - MCP;
   - skill, plugin y marketplace.
3. Implementar fase a fase, ejecutando los tests al final de cada una.
4. Si hay una duda fiscal que afecte a un cálculo, preguntarme en vez de asumir.
