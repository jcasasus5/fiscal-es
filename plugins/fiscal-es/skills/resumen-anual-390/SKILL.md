---
name: resumen-anual-390
description: Prepara el modelo 390 (declaración-resumen anual del IVA) de un autónomo en España a partir del libro registro y de los 303 presentados del año. Úsala cuando el usuario pida hacer o revisar el 390, el resumen anual del IVA, cuando prepare el 303 del 4T (el 390 se presenta en el mismo plazo de enero) o cuando quiera registrar 303 que presentó a mano. Trabaja con las tools MCP del servidor fiscal-es.
---

# Resumen anual del IVA (modelo 390)

El 390 resume en un único documento los cuatro 303 del año. Se presenta del **1 al 30 de
enero**, junto con el 303 del 4T. Lo presentan todos los que hacen 303 trimestrales salvo
los exonerados: quienes solo tienen módulos o arrendamiento de locales urbanos, y los
del SII. **Un profesional en régimen general no está exonerado.** Si dudas de si el
usuario lo está, consúltalo con `consultar_instrucciones_390` y pregúntale; no lo supongas.

Las reglas de la skill `iva-trimestral` se aplican igual:
- No calcules importes.
- No inventes cómo se rellena una casilla; cita las instrucciones oficiales.
- No presentes nada.
- Pregunta ante cualquier duda.

## De dónde sale cada dato

| Dato | Fuente |
|---|---|
| IVA devengado y deducible por tipo, volumen de operaciones | Libro registro (facturas del año) |
| Lo ingresado en el año [95], cuotas compensadas [85], resultado del 4T [97]/[98] | Los **303 presentados**, registrados con su justificante |
| Apellidos y nombre por separado, actividad, clave, epígrafe IAE, 347 | Perfil fiscal (`ver_perfil(ejercicio, modelo='390')`) |

Los 303 presentados se guardan en el libro local con `registrar_303_presentado`, junto a
los que genera la herramienta. Así todo queda registrado de la misma forma y sirve para
el 390 y para el futuro.

## Flujo

1. **Diseño de registro:** `comprobar_diseno_390(ejercicio)`. Si hay uno nuevo y es
   compatible, `instalar_diseno_390(ejercicio)`. Si no es compatible, para y explícalo.

2. **Perfil:** `ver_perfil(ejercicio, modelo='390')`. Pregunta lo que falte. La mejor
   fuente es el **390 del año anterior**, si lo presentó (apartados 1 y 3); si no, su alta
   censal (036/037) o "Mis datos censales". La clave de actividad se pregunta con la lista
   de claves que da la tool. Que un profesional suela ser A05 no es motivo para suponerlo.
   Al final, `confirmar_perfil('<ejercicio>-4T', fuente)`.

3. **Los cuatro 303 del año:** `listar_autoliquidaciones(ejercicio)`.
   - Los generados aquí y ya presentados que aún figuran como `generada`: pide el
     justificante y regístralo.
   - Los que **no estén** (presentados a mano antes de usar la herramienta, o por una
     gestoría): pide al usuario el **justificante PDF** de cada uno. Si no lo tiene,
     explícale dónde descargarlo: en la Sede, "Mi área personal" > "Mis expedientes" (o
     la consulta de declaraciones presentadas del modelo 303). Si lo presentó una
     gestoría, que se lo pida a ella.
   - Lee cada justificante y llama a `registrar_303_presentado` con:
     - el trimestre;
     - las casillas que tengan importe (siempre la 71);
     - el tipo de declaración ("NEGATIVA/SIN ACTIVIDAD/RESULTADO CERO" = N,
       domiciliación = U, ingreso = I, compensar = C, devolver = D);
     - el número de justificante (13 dígitos), la fecha de presentación y la ruta del PDF.

     La tool comprueba la aritmética y que los datos aparecen en el PDF. Si falla, vuelve
     a leer el documento; no fuerces los números.
   - Si en algún trimestre no estaba dado de alta en la actividad:
     `marcar_303_no_presentado(trimestre, motivo)`, solo si él lo confirma.

4. **Facturas:** el libro registro tiene que contener las facturas de todo el año. Si
   faltan las de trimestres que se hicieron a mano, búscalas y regístralas como en el
   303 (`registrar_factura`).

5. **Calcula:** `calcular_390(ejercicio)`. Cruza cada trimestre del libro con su 303
   presentado. Explica al usuario el resultado y el estado de cada trimestre. Para cada
   bloqueo:
   - "no cuadra": faltan o sobran facturas en el libro, o el 303 se presentó mal (en ese
     caso puede requerir una rectificativa: recomiéndale un asesor).
   - "falta el 303": vuelve al paso 3.
   - Fuera de alcance (complementarias, cuotas a compensar generadas en el año [662],
     regímenes especiales): díselo tal cual.

6. **Genera:** `generar_390(ejercicio)`. Dale la ruta del `.390` y los pasos: Sede →
   Modelo 390 → "Presentación (con fichero)" → importar → revisar → validar, firmar y
   enviar.
   - Si el 303 del 4T solo consta como generado, recuérdale presentarlo tal cual (o
     registrar su justificante) antes del 390.
   - Cuando presente el 390, guarda su justificante.

## Dudas

`consultar_instrucciones_390(ejercicio, consulta)` busca en las instrucciones oficiales
(PDF de la ficha G412). Las de un ejercicio se publican al acercarse el plazo. Si las del
año aún no están, consulta las del anterior y **avisa** de que son del año anterior.
`info_casilla(casilla, ejercicio, modelo='390')` dice qué es cada casilla en el diseño.
