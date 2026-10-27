# Investigación: modelo 390 (declaración-resumen anual del IVA)

Fecha: 2026-10-27.
Objetivo: añadir el 390 al plugin con el mismo enfoque que el 303, es decir, fichero
oficial generado de forma determinista para importar en la Sede.

## ¿Quién está obligado?

Según el [manual práctico de IVA 2026 de la AEAT](https://sede.agenciatributaria.gob.es/Sede/ayuda/manuales-videos-folletos/manuales-practicos/manual-iva-2026/capitulo-09-declaraciones-informativas-iva-379/declaracion-resumen-anual-modelo-390/obligados-presentar-declaracion.html),
deben presentarlo todos los sujetos pasivos que presentan autoliquidaciones periódicas
de IVA. Están exonerados (Orden EHA/3111/2009, art. 1):

- Quienes tributan solo en territorio común, presentan trimestralmente y realizan
  **exclusivamente** actividades en régimen simplificado o de arrendamiento de
  inmuebles urbanos. Estos rellenan la página 4 del 303 del 4T.
- Quienes llevan los libros registro a través de la Sede (SII).

Un profesional en régimen general **no está exonerado**. Plazo: del 1 al 30 de enero
del año siguiente, junto con el 303 del 4T.

## Diseño de registro

- Publicado en la misma página que el del 303:
  [`dr390e2026.xlsx`](https://sede.agenciatributaria.gob.es/static_files/Sede/Disenyo_registro/DR_300_399/archivos_26/dr390e2026.xlsx),
  "Ejercicio 2026 y siguientes".
- **Mismo formato que el 303**: cabecera `<T3900EEEE0A0000><AUX>…</AUX>`, páginas
  `<T390XXXXX>…</T390XXXXX>` y cierre `</T3900EEEE0A0000>`. Los tipos de campo y el
  relleno son los mismos: An con blancos a la derecha, Num con ceros a la izquierda,
  N con `N` delante si es negativo. Los importes van en 17 posiciones (15 enteros y
  2 decimales).
- Las hojas se llaman "Pág. 0" … "Pág. 8" y hay una "Pág. 2 bis". El código de página
  sale de la constante del campo "Página" (`01000`, `02B00`, …).
- Páginas:

  | Página | Contenido |
  |---|---|
  | 01 | Identificación, datos estadísticos y representante |
  | 02 y 02B | IVA devengado y total de cuotas ([47]) |
  | 03 y 04 | IVA deducible ([64]) y resultado del régimen general ([65]) |
  | 05 | Régimen simplificado |
  | 06 | Resultado anual, territorio, resultados de las liquidaciones y volumen de operaciones |
  | 07 | Operaciones específicas y prorratas |
  | 08 | Deducciones diferenciadas |

- **Detalles que obligan a adaptar el generador:**
  - Algunas casillas aparecen dos veces en la misma página: [658], [84], [659] y [112]
    están en la sección 7 y otra vez en la sección 8 de la página 6.
  - Algunos campos no tienen número de casilla (representante, otras actividades).
  - El fin de registro se describe como "Indentificador de Fin de registro".

## Presentación

En la [ficha G412](https://sede.agenciatributaria.gob.es/Sede/procedimientoini/G412.shtml)
está la opción "Modelo 390. Ejercicio AAAA. Presentación (con fichero)". El formulario
del ejercicio 2026 se abrirá en enero de 2027.

## Instrucciones oficiales

Están en G412, en PDF, uno por ejercicio ("Instrucciones 2025", "Instrucciones 2024").
El texto se extrae bien. Casillas clave según las instrucciones de 2025:

- **[33]/[34]:** suma de bases y cuotas devengadas. **[47]** = [34] más los recargos
  de equivalencia.
- **IVA deducible en operaciones interiores corrientes, por tipo:**
  - 4 %: [190]/[191]
  - 10 %: [603]/[604]
  - 21 %: [605]/[606]
  - Total: [48]/[49]
- **[64]** suma de deducciones; **[65]** resultado del régimen general.
- **Sección 7** (solo quien tributa exclusivamente a la Administración del Estado):
  - [84] = [65] + [83] + [658]
  - [85] = cuotas de ejercicios anteriores aplicadas en el año, es decir, la suma de
    las casillas 78 de los 303 del ejercicio
  - [86] = [84] + [659] − [85]
- **Sección 8:** solo para quien tributa a varias Administraciones (forales).
- **Sección 9:**
  - [95]: suma de lo que salió a ingresar en los 303 del ejercicio.
  - [97]/[98]: resultado del último periodo si fue a compensar o a devolver.
  - [662]: cuotas a compensar generadas en periodos distintos del último que no se
    aplicaron en el resto del ejercicio.
- **[99]:** importe, sin IVA, de las entregas y servicios en régimen general.
  **[108]** = [99] + … (artículo 121 LIVA).
- **Datos estadísticos:**
  - Actividad principal.
  - Clave: A01 arrendadores, A03 resto de actividades empresariales, A04 profesionales
    artísticos o deportivos, A05 resto de actividades profesionales, etc.
  - Epígrafe del IAE.
  - Marca de la declaración anual de operaciones con terceros (347).

## Datos necesarios y de dónde salen

| Dato | Fuente |
|---|---|
| Bases y cuotas devengadas y deducibles por tipo, y volumen de operaciones | Libro registro (facturas del año) |
| [85], [95], [97]/[98] | Los 303 **presentados** del ejercicio, con sus justificantes |
| Apellidos y nombre por separado, actividad, clave, epígrafe IAE, 347 | Perfil fiscal: último 390 presentado, alta censal (036/037) o preguntar al usuario |

Los 303 presentados se guardan en el mismo libro registro local (tabla
`autoliquidaciones` de `libro.db`, dentro de `FISCAL_DATA_DIR`), con una copia del
justificante:

- Los que genera la herramienta quedan como `generada`.
- Al presentarse, pasan a `presentada` con el número de justificante.
- Los que el usuario presentó a mano antes de tener el plugin se registran leyendo
  su justificante.

Antes de generar el 390, la herramienta cruza el libro registro con lo presentado. Si no
cuadran, avisa en lugar de esconder la diferencia.

## Alcance inicial del 390

El mismo que el del 303: régimen general, territorio común, trimestral, operaciones
interiores y tipos 21/10/4 %. Además, quedan pendientes con aviso:

- autoliquidaciones complementarias y declaraciones sustitutivas;
- cuotas a compensar generadas en periodos distintos del último ([662]);
- varias actividades y prorrata;
- regímenes especiales.

## Incertidumbres que hay que verificar al importar

- Qué páginas exige el validador de la Sede cuando están a cero. Se emiten 01, 02,
  02B, 03, 04, 06 y 07, y se omiten la 05 (simplificado) y la 08 (deducciones
  diferenciadas).
- La fórmula de [86] en 2026 puede incluir [112] (pago a cuenta de carburantes), que
  aparece en la sección 7 del diseño de 2026. Para el alcance soportado vale 0.
