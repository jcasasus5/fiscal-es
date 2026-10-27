"""Casos de uso compartidos por el servidor MCP y la CLI.

Todo devuelve estructuras JSON-serializables (dict/list/str) para que la capa MCP
y la CLI sean finas.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from .config import Rutas, rutas
from .core import (alcance, calculo303, calculo390, diseno, disenos_aeat, fichero, fichero303, fichero390,
                   instrucciones_aeat, pdf_check, validacion)
from .core import iban as ibanmod
from .core import nif as nifmod
from .core.importes import CERO, formato_es, parse_importe, redondear
from .core.libro import Autoliquidaciones, Duplicada, Libro
from .core.modelos import CLAVES_ACTIVIDAD, PREGUNTAS_PERFIL, Factura, Incidencia, Perfil, campos_factura
from .core.periodo import Trimestre, plazo_303, proximos_plazos

VALIDEZ_COMPROBACION = timedelta(days=7)


class Servicio:
    def __init__(self, base: str | Path | None = None):
        self.rutas: Rutas = rutas(base)
        self.libro = Libro(self.rutas.db)
        self.autoliqs = Autoliquidaciones(self.libro)

    def close(self) -> None:
        self.libro.close()

    # ------------------------------------------------------------------ perfil
    def perfil(self) -> Perfil:
        if not self.rutas.perfil.exists():
            return Perfil()
        return Perfil.from_dict(json.loads(self.rutas.perfil.read_text(encoding="utf-8")))

    def ver_perfil(self, trimestre: str | None = None, modelo: str = "303") -> dict[str, Any]:
        """Para el 303, `trimestre` es '2027-1T'; para el 390 basta el ejercicio ('2026' o '2026-4T')."""
        p = self.perfil()
        if modelo == "390":
            ejercicio = int(str(trimestre)[:4]) if trimestre else None
            pendientes = calculo303.preguntas_pendientes(p, None, "390")
            problemas = calculo390.comprobar_perfil_390(p, ejercicio) if ejercicio else []
        else:
            t = Trimestre.parse(trimestre) if trimestre else None
            pendientes = calculo303.preguntas_pendientes(p, t)
            problemas = calculo303.comprobar_perfil(p, t) if t else []
        return {
            "perfil": p.to_dict(),
            "preguntas_pendientes": [{"campo": c, **PREGUNTAS_PERFIL[c]} for c in pendientes],
            "problemas": problemas,
            "confirmado_para": p.confirmado_trimestre,
            "fuentes_recomendadas": FUENTES_PERFIL,
            "ruta": str(self.rutas.perfil),
        }

    def _guardar_perfil(self, actual: dict[str, Any], nuevo: Perfil, motivo: str | None) -> dict[str, Any]:
        datos = nuevo.to_dict()
        self.rutas.perfil.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.chmod(self.rutas.perfil, 0o600)
        cambiados = {k: {"antes": actual.get(k), "despues": v} for k, v in datos.items() if actual.get(k) != v}
        if cambiados:
            with open(self.rutas.base / "perfil_historial.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": _ahora(), "cambios": cambiados, "motivo": motivo}, ensure_ascii=False) + "\n")
        return {"perfil": datos, "cambiados": sorted(cambiados)}

    def actualizar_perfil(self, cambios: dict[str, Any], motivo: str | None = None) -> dict[str, Any]:
        reservados = {"confirmado_trimestre", "confirmado_fecha", "confirmado_fuente"} & set(cambios)
        if reservados:
            raise ValueError("La confirmación del perfil se hace con confirmar_perfil, no con actualizar_perfil.")
        actual = self.perfil().to_dict()
        nuevo = Perfil.from_dict({**actual, **cambios})
        if nuevo.nif:
            nuevo.nif = nifmod.normalizar(nuevo.nif)
            if not nifmod.es_valido(nuevo.nif):
                raise ValueError(f"NIF no válido: {nuevo.nif}")
        if nuevo.iban:
            nuevo.iban = ibanmod.normalizar(nuevo.iban)
            if not ibanmod.es_valido(nuevo.iban):
                raise ValueError("IBAN no válido (dígitos de control).")
        for campo, valores in (
            ("forma_pago", ("domiciliacion", "ingreso")),
            ("regimen", ("general", "simplificado")),
            ("periodicidad", ("trimestral", "mensual")),
            ("territorio", ("comun", "foral")),
        ):
            if getattr(nuevo, campo) not in (None, *valores):
                raise ValueError(f"'{campo}' debe ser uno de {valores}.")
        for campo in ("criterio_caja", "destinatario_criterio_caja", "sii", "registro_devolucion_mensual",
                      "prorrata", "concurso_acreedores", "exonerado_390"):
            if getattr(nuevo, campo) not in (None, True, False):
                raise ValueError(f"'{campo}' debe ser true, false o null (sin confirmar).")
        if nuevo.cuotas_a_compensar is not None and nuevo.cuotas_a_compensar < 0:
            raise ValueError("'cuotas_a_compensar' no puede ser negativo.")
        if nuevo.operaciones_347 not in (None, True, False):
            raise ValueError("'operaciones_347' debe ser true, false o null (sin confirmar).")
        if nuevo.clave_actividad:
            nuevo.clave_actividad = nuevo.clave_actividad.strip().upper()
            if nuevo.clave_actividad not in CLAVES_ACTIVIDAD:
                raise ValueError(f"'clave_actividad' debe ser una de {list(CLAVES_ACTIVIDAD)}.")
        for campo, maximo in (("apellidos", 60), ("nombre_pila", 20), ("actividad_principal", 40), ("epigrafe_iae", 4)):
            valor = getattr(nuevo, campo)
            if valor and len(valor.strip()) > maximo:
                raise ValueError(f"'{campo}' admite como máximo {maximo} caracteres en el modelo 390.")
        return self._guardar_perfil(actual, nuevo, motivo)

    def confirmar_perfil(self, trimestre: str, fuente: str) -> dict[str, Any]:
        """Registra que el usuario ha confirmado que su perfil vale para este trimestre."""
        if not fuente or not fuente.strip():
            raise ValueError("Indica de dónde sale la confirmación (p. ej. 'el usuario lo confirma', 'justificante 303 2026-3T').")
        t = Trimestre.parse(trimestre)
        actual = self.perfil()
        pendientes = calculo303.preguntas_pendientes(actual, t)
        if pendientes:
            raise ValueError("No se puede confirmar: faltan datos por preguntar: " + ", ".join(pendientes))
        nuevo = Perfil.from_dict(actual.to_dict())
        nuevo.confirmado_trimestre, nuevo.confirmado_fecha, nuevo.confirmado_fuente = str(t), _ahora(), fuente
        res = self._guardar_perfil(actual.to_dict(), nuevo, f"Confirmación para {t}: {fuente}")
        res["problemas"] = calculo303.comprobar_perfil(nuevo, t)
        return res

    # ---------------------------------------------------------------- facturas
    def _verificar_pdf(self, f: Factura, ruta_pdf: str | None) -> tuple[list[Incidencia], str]:
        if not ruta_pdf:
            return [Incidencia("sin_pdf", "aviso", "Sin PDF asociado: los datos no se han podido verificar contra el documento.")], "sin_pdf"
        v = pdf_check.verificar(f, pdf_check.extraer_texto(Path(ruta_pdf)))
        if v.estado == "no_coincide":
            return [Incidencia(
                "pdf_no_coincide", "revisar",
                "Estos datos no aparecen en el PDF: " + "; ".join(v.no_encontrados)
                + ". Revisa la lectura y corrige, o confirma si el PDF los muestra de otra forma.",
            )], v.estado
        if v.estado == "sin_texto":
            return [Incidencia("pdf_sin_texto", "aviso", "El PDF no tiene texto (¿escaneado?): revisa los datos a mano.")], v.estado
        return [], v.estado

    def _archivar_pdf(self, ruta: Path, f: Factura, sha: str) -> Path:
        destino = self.rutas.base / "facturas" / str(f.trimestre) / f.tipo
        destino.mkdir(parents=True, exist_ok=True)
        archivo = destino / f"{sha[:12]}_{ruta.name}"
        if not archivo.exists():
            shutil.copy2(ruta, archivo)
        return archivo

    def registrar_factura(self, datos: dict[str, Any], ruta_pdf: str | None = None,
                          origen: str | None = None, trimestre: str | None = None) -> dict[str, Any]:
        f = Factura.from_dict(datos)
        sha = None
        pdf_guardado = None
        if ruta_pdf:
            ruta = Path(ruta_pdf).expanduser()
            if not ruta.is_file():
                raise FileNotFoundError(f"No existe el PDF: {ruta}")
            sha = pdf_check.sha256(ruta)
            ruta_pdf = str(ruta)
        incidencias = validacion.validar(f, self.perfil())
        inc_pdf, estado_pdf = self._verificar_pdf(f, ruta_pdf)
        incidencias += inc_pdf
        if trimestre:
            esperado = Trimestre.parse(trimestre)
            if f.trimestre != esperado:
                incidencias.append(Incidencia(
                    "otro_trimestre", "aviso",
                    f"La factura es de {f.trimestre} (fecha de devengo {f.fecha_devengo}), no de {esperado}: se registra en {f.trimestre}.",
                ))
        try:
            if ruta_pdf and sha:
                dup = self.libro.buscar_duplicada(f, sha)
                if dup:
                    raise Duplicada(*dup)
                pdf_guardado = str(self._archivar_pdf(Path(ruta_pdf), f, sha))
            r = self.libro.alta(f, incidencias, pdf_path=pdf_guardado, pdf_sha256=sha,
                                verificacion_pdf=estado_pdf, origen=origen or ruta_pdf)
        except Duplicada as d:
            return {"resultado": "duplicada", "motivo": d.motivo, "existente": d.existente.to_dict()}
        return {"resultado": "registrada" if r.estado == "valida" else "pendiente", "factura": r.to_dict()}

    def listar_facturas(self, trimestre: str | None = None, estado: str | None = None) -> dict[str, Any]:
        t = Trimestre.parse(trimestre) if trimestre else None
        regs = self.libro.listar(t, estado)
        resumen: dict[str, int] = {}
        for r in regs:
            resumen[r.estado] = resumen.get(r.estado, 0) + 1
        return {"facturas": [r.to_dict() for r in regs], "resumen": resumen}

    def corregir_factura(self, factura_id: int, cambios: dict[str, Any], motivo: str) -> dict[str, Any]:
        previo = self.libro.obtener(factura_id)
        datos = {**previo.factura.to_dict(), **cambios}
        f = Factura.from_dict(datos)
        incidencias = validacion.validar(f, self.perfil())
        inc_pdf, estado_pdf = self._verificar_pdf(f, previo.pdf_path)
        try:
            r = self.libro.actualizar(factura_id, f, incidencias + inc_pdf, motivo, verificacion_pdf=estado_pdf)
        except Duplicada as d:
            return {"resultado": "duplicada", "motivo": d.motivo, "existente": d.existente.to_dict()}
        return {"resultado": "corregida", "factura": r.to_dict()}

    def confirmar_factura(self, factura_id: int, motivo: str) -> dict[str, Any]:
        return {"resultado": "confirmada", "factura": self.libro.confirmar(factura_id, motivo).to_dict()}

    def descartar_factura(self, factura_id: int, motivo: str) -> dict[str, Any]:
        return {"resultado": "descartada", "factura": self.libro.descartar(factura_id, motivo).to_dict()}

    def reactivar_factura(self, factura_id: int, motivo: str) -> dict[str, Any]:
        return {"resultado": "reactivada", "factura": self.libro.reactivar(factura_id, motivo).to_dict()}

    def historial_factura(self, factura_id: int) -> dict[str, Any]:
        return {"factura": self.libro.obtener(factura_id).to_dict(), "eventos": self.libro.eventos(factura_id)}

    # ------------------------------------------------------ diseños de registro
    def _registro_comprobacion(self) -> Path:
        return self.rutas.disenos / "ultima_comprobacion.json"

    def _ultima_comprobacion(self, clave: str) -> dict[str, Any] | None:
        p = self._registro_comprobacion()
        if not p.exists():
            return None
        datos = json.loads(p.read_text(encoding="utf-8")).get(clave)
        if not datos:
            return None
        cuando = datetime.fromisoformat(datos["ts"])
        return datos if datetime.now(timezone.utc) - cuando <= VALIDEZ_COMPROBACION else None

    def _guardar_comprobacion(self, clave: str, estado: str, archivo: str | None) -> None:
        p = self._registro_comprobacion()
        todo = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        todo[clave] = {"ts": _ahora(), "estado": estado, "archivo": archivo}
        p.write_text(json.dumps(todo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _comprobar_diseno(self, modelo: str, t: Trimestre, clave: str) -> dict[str, Any]:
        info = disenos_aeat.comprobar(t, self.rutas.disenos, modelo=modelo)
        if info["estado"] == "al_dia":
            self._guardar_comprobacion(clave, "al_dia", info["publicado"]["archivo"])
        return info

    def _instalar_diseno(self, modelo: str, t: Trimestre | None, clave: str | None, ruta_xlsx: str | None,
                         desde: str | None) -> dict[str, Any]:
        if ruta_xlsx:
            return disenos_aeat.instalar(self.rutas.disenos, ruta_local=Path(ruta_xlsx).expanduser(), desde=desde,
                                         modelo=modelo)
        if t is None:
            raise ValueError("Indica el periodo para elegir el diseño publicado aplicable.")
        pubs = [p for p in disenos_aeat.consultar_publicados(modelo)
                if p.ejercicio_desde and Trimestre(p.ejercicio_desde, 1) <= t]
        if not pubs:
            raise LookupError(f"La AEAT no publica ningún diseño del modelo {modelo} aplicable a {t}.")
        pub = max(pubs, key=lambda p: (p.ejercicio_desde, p.actualizado or date.min))
        res = disenos_aeat.instalar(self.rutas.disenos, pub=pub, desde=desde, modelo=modelo)
        if res["compatibilidad"]["compatible"] and clave:
            self._guardar_comprobacion(clave, "al_dia", pub.archivo)
        return res

    def comprobar_diseno_303(self, trimestre: str) -> dict[str, Any]:
        t = Trimestre.parse(trimestre)
        return self._comprobar_diseno("303", t, str(t))

    def instalar_diseno_303(self, trimestre: str | None = None, ruta_xlsx: str | None = None,
                            desde: str | None = None) -> dict[str, Any]:
        t = Trimestre.parse(trimestre) if trimestre else None
        return self._instalar_diseno("303", t, str(t) if t else None, ruta_xlsx, desde)

    def comprobar_diseno_390(self, ejercicio: int) -> dict[str, Any]:
        return self._comprobar_diseno("390", Trimestre(int(ejercicio), 4), f"390-{int(ejercicio)}")

    def instalar_diseno_390(self, ejercicio: int | None = None, ruta_xlsx: str | None = None,
                            desde: str | None = None) -> dict[str, Any]:
        t = Trimestre(int(ejercicio), 4) if ejercicio else None
        return self._instalar_diseno("390", t, f"390-{int(ejercicio)}" if ejercicio else None, ruta_xlsx, desde)

    def disenos_instalados(self) -> list[dict[str, Any]]:
        return [
            {"modelo": d.entrada.modelo, "archivo": d.entrada.archivo, "desde": d.entrada.desde,
             "actualizado": d.entrada.actualizado, "origen": d.origen, "sha256": d.entrada.sha256}
            for d in diseno.disponibles(self.rutas.disenos)
        ]

    # ------------------------------------------------- ayuda y documentación
    def capacidades(self) -> dict[str, Any]:
        return alcance.capacidades()

    def _consultar_instrucciones(self, modelo: str, ejercicio: int, periodo: str | None, consulta: str | None,
                                 max_resultados: int) -> dict[str, Any]:
        cache = self.rutas.base / "cache_aeat"
        paginas = instrucciones_aeat.paginas_ejercicio(ejercicio, cache, modelo)
        base: dict[str, Any] = {
            "modelo": modelo,
            "ejercicio": ejercicio,
            "periodo": periodo,
            "fuente": instrucciones_aeat.PROCEDIMIENTOS[modelo],
            "paginas": [{"titulo": p.titulo, "url": p.url} for p in paginas],
        }
        if not consulta:
            return {**base, "indice": instrucciones_aeat.indice_secciones(paginas, periodo)}
        resultados = instrucciones_aeat.buscar(paginas, consulta, periodo, max_resultados)
        base["resultados"] = resultados
        if not resultados:
            base["nota"] = (
                "Las instrucciones oficiales de este ejercicio no tratan esto de forma reconocible. No lo supongas: "
                "prueba otras palabras o el número de casilla, y si sigue sin aparecer, díselo al usuario "
                "(puede requerir la normativa del IVA o un asesor)."
            )
        else:
            base["nota"] = "Cita el texto y la URL al usuario. Es texto literal de la AEAT: no lo completes con suposiciones."
        return base

    def consultar_instrucciones_303(self, trimestre: str, consulta: str | None = None,
                                    max_resultados: int = 6) -> dict[str, Any]:
        """Busca en las instrucciones oficiales de la AEAT del ejercicio del trimestre."""
        t = Trimestre.parse(trimestre)
        return self._consultar_instrucciones("303", t.ejercicio, t.codigo, consulta, max_resultados)

    def consultar_instrucciones_390(self, ejercicio: int, consulta: str | None = None,
                                    max_resultados: int = 6) -> dict[str, Any]:
        """Busca en las instrucciones oficiales del 390. Si las del ejercicio aún no están publicadas,
        devuelve un error con los ejercicios disponibles (el agente puede consultar el anterior y avisar)."""
        return self._consultar_instrucciones("390", int(ejercicio), None, consulta, max_resultados)

    def info_casilla(self, casilla: str, periodo: str, modelo: str = "303") -> dict[str, Any]:
        """Qué es una casilla según el diseño de registro y si la herramienta la calcula.
        `periodo`: trimestre ('2026-3T') para el 303; ejercicio ('2026') para el 390."""
        t = Trimestre(int(str(periodo)[:4]), 4) if modelo == "390" else Trimestre.parse(periodo)
        num = str(casilla).strip().strip("[]")
        disp = diseno.seleccionar(t, self.rutas.disenos, modelo)
        d = diseno.cargar(disp)
        apariciones = []
        for cod, pag in d.paginas.items():
            for c in pag.campos:
                if c.casilla and num.isdigit() and int(c.casilla) == int(num):
                    apariciones.append({
                        "pagina": cod,
                        "descripcion": c.descripcion,
                        "tipo": c.tipo,
                        "longitud": c.lon,
                        "validacion": " ".join(x for x in (c.validacion, c.contenido) if x),
                        "la_calcula_la_herramienta": alcance.calculada(cod, c.casilla, modelo) is not None,
                    })
        if not apariciones:
            raise LookupError(f"La casilla {num} no aparece en el diseño {disp.entrada.archivo}.")
        consulta = (f"consultar_instrucciones_390({t.ejercicio}, 'casilla {num}')" if modelo == "390"
                    else f"consultar_instrucciones_303('{t}', 'casilla {num}')")
        return {
            "modelo": modelo,
            "casilla": num,
            "diseno": disp.entrada.archivo,
            "apariciones": apariciones,
            "sugerencia": f"Para saber cómo se rellena: {consulta}.",
        }

    # ------------------------------------------------------------------ 303
    def _calcular(self, t: Trimestre, opcion_negativo: str | None) -> calculo303.Resultado303:
        return calculo303.calcular(t, self.libro.listar(t), self.perfil(), opcion_negativo)  # type: ignore[arg-type]

    def calcular_303(self, trimestre: str, opcion_negativo: str | None = None) -> dict[str, Any]:
        t = Trimestre.parse(trimestre)
        res = self._calcular(t, opcion_negativo)
        out = res.to_dict()
        try:
            d = diseno.seleccionar(t, self.rutas.disenos)
            out["diseno"] = d.entrada.archivo
        except LookupError as e:
            out["diseno"] = None
            out["bloqueos"].append(str(e))
            out["generable"] = False
        if not self._ultima_comprobacion(str(t)):
            out["avisos"].append(
                "No se ha comprobado en los últimos 7 días si la AEAT ha publicado un diseño de registro nuevo: "
                "ejecuta comprobar_diseno_303 antes de generar."
            )
        p = plazo_303(t)
        out["plazo"] = {"inicio": p.inicio.isoformat(), "fin": p.fin.isoformat(),
                        "fin_domiciliacion": p.fin_domiciliacion.isoformat()}
        return out

    def generar_303(self, trimestre: str, opcion_negativo: str | None = None,
                    ignorar_pendientes: bool = False) -> dict[str, Any]:
        t = Trimestre.parse(trimestre)
        perfil = self.perfil()
        res = self._calcular(t, opcion_negativo)
        if ignorar_pendientes:
            quitados = [b for b in res.bloqueos if b.startswith("Factura pendiente")]
            res.bloqueos = [b for b in res.bloqueos if not b.startswith("Factura pendiente")]
            if quitados:
                res.avisos.append(f"Se han dejado fuera {len(quitados)} facturas pendientes a petición del usuario.")
        if res.bloqueos:
            return {"generado": False, "bloqueos": res.bloqueos, "calculo": res.to_dict()}
        disp = diseno.seleccionar(t, self.rutas.disenos)
        d = diseno.cargar(disp)
        contenido = fichero303.generar(d, res, perfil)
        # Comprobación de ida y vuelta: lo escrito se vuelve a leer con el diseño.
        leido = fichero303.leer(d, contenido)
        for pag in ("01", "03"):
            for cas, v in res.casillas[pag].items():
                campo = fichero303.campo(d.paginas[pag], fichero303.ESPEC, f"[{cas}]")
                if leido[pag][f"[{cas}]"] != fichero303.formatear(campo, v):
                    raise RuntimeError(f"Verificación interna fallida en la casilla {cas}.")
        carpeta = self.rutas.salida / str(t)
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = carpeta / fichero303.nombre_fichero(res, perfil)
        ruta.write_bytes(contenido)
        resumen = res.to_dict()
        resumen.update({"diseno": disp.entrada.archivo, "fichero": str(ruta), "generado_en": _ahora()})
        (carpeta / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        planas = {c: v for pag in res.casillas.values() for c, v in pag.items()}
        self.autoliqs.guardar_generada("303", t.ejercicio, t.codigo, planas, res.tipo_declaracion,
                                       res.sin_actividad, str(ruta))
        avisos = list(res.avisos)
        if not self._ultima_comprobacion(str(t)):
            avisos.append("No se ha comprobado recientemente si hay un diseño de registro nuevo (comprobar_diseno_303).")
        return {
            "generado": True,
            "fichero": str(ruta),
            "diseno": disp.entrada.archivo,
            "resultado": formato_es(res.resultado),
            "tipo_declaracion": calculo303.TEXTO_TIPO[res.tipo_declaracion],
            "sin_actividad": res.sin_actividad,
            "casillas": resumen["casillas"],
            "explicacion": res.explicacion,
            "avisos": avisos,
            "siguientes_pasos": PASOS_SEDE + [
                "Cuando lo hayas presentado, pásame el justificante para registrarlo (registrar_303_presentado): "
                "así queda guardado y servirá para el 390."
            ],
        }

    # ------------------------------------------------- 303 presentados (registro)
    def registrar_303_presentado(self, trimestre: str, casillas: dict[str, Any], tipo_declaracion: str,
                                 justificante: str, fecha_presentacion: str | None = None,
                                 ruta_pdf: str | None = None, sin_actividad: bool | None = None,
                                 origen: str | None = None) -> dict[str, Any]:
        """Guarda un 303 ya presentado (leído de su justificante) en el libro, junto a los generados."""
        t = Trimestre.parse(trimestre)
        just = re.sub(r"\s", "", str(justificante or ""))
        if not re.fullmatch(r"\d{13}", just):
            raise ValueError("El número de justificante del 303 tiene 13 dígitos (aparece en el PDF como 'Número de justificante').")
        tipo = (tipo_declaracion or "").strip().upper()
        if tipo not in calculo303.TEXTO_TIPO and tipo not in ("G", "V", "X"):
            raise ValueError(f"Tipo de declaración no válido: {tipo_declaracion} (I, U, N, C, D, G, V o X).")
        cas: dict[str, Any] = {}
        for k, v in (casillas or {}).items():
            n = str(k).strip().strip("[]")
            if not n.isdigit():
                raise ValueError(f"Casilla no válida: {k}")
            cas[n.zfill(2)] = redondear(parse_importe(v))
        errores = _aritmetica_303(cas)
        if "71" not in cas:
            errores.insert(0, "Falta la casilla 71 (resultado).")
        importes = {c: v for c, v in cas.items() if c != "65"}
        if sin_actividad and any(importes.values()):
            errores.append("Marcada como sin actividad pero tiene importes distintos de cero.")
        fecha = _fecha_iso(fecha_presentacion) if fecha_presentacion else None
        pdf_guardado = sha = None
        if ruta_pdf:
            ruta = Path(ruta_pdf).expanduser()
            if not ruta.is_file():
                raise FileNotFoundError(f"No existe el PDF: {ruta}")
            texto = pdf_check.extraer_texto(ruta)
            if len(texto.strip()) >= 20:
                if just not in re.sub(r"\s", "", texto):
                    errores.append(f"El justificante {just} no aparece en el PDF: ¿es el documento correcto?")
                faltan = [f"[{c}] {formato_es(v)}" for c, v in importes.items() if v and not pdf_check.aparece_importe(texto, v)]
                if faltan:
                    errores.append("Estos importes no aparecen en el PDF: " + ", ".join(faltan) + ". Revisa la lectura.")
        if errores:
            raise ValueError("No se registra el 303: " + " | ".join(errores))
        if ruta_pdf:
            sha = pdf_check.sha256(Path(ruta_pdf).expanduser())
            carpeta = self.rutas.base / "autoliquidaciones" / "303" / str(t.ejercicio)
            carpeta.mkdir(parents=True, exist_ok=True)
            destino = carpeta / f"{t.codigo}_{just}.pdf"
            shutil.copy2(Path(ruta_pdf).expanduser(), destino)
            pdf_guardado = str(destino)
        a, generada = self.autoliqs.registrar_presentada(
            "303", t.ejercicio, t.codigo, cas, tipo,
            bool(sin_actividad) if sin_actividad is not None else not any(importes.values()),
            just, fecha, pdf_guardado, sha, origen or ("justificante PDF" if ruta_pdf else "datos del usuario"),
        )
        out: dict[str, Any] = {"resultado": "registrado", "autoliquidacion": a.to_dict()}
        if generada:
            dif = sorted(c for c in set(generada.casillas) | set(cas)
                         if generada.casilla(c) != cas.get(c, CERO) and c != "65")
            if dif:
                out["aviso"] = (
                    "El 303 presentado no coincide con el que generó la herramienta en las casillas "
                    + ", ".join(dif) + ". Revisa si se modificó en la Sede o si hay que corregir el libro."
                )
        return out

    def marcar_303_no_presentado(self, trimestre: str, motivo: str) -> dict[str, Any]:
        t = Trimestre.parse(trimestre)
        return {"resultado": "registrado", "autoliquidacion": self.autoliqs.marcar_no_presentada("303", t.ejercicio, t.codigo, motivo).to_dict()}

    def listar_autoliquidaciones(self, ejercicio: int | None = None, modelo: str | None = None) -> dict[str, Any]:
        lista = self.autoliqs.listar(modelo, int(ejercicio) if ejercicio else None)
        return {"autoliquidaciones": [a.to_dict() for a in lista], "donde_obtener_justificantes": calculo390.DONDE_JUSTIFICANTES}

    # ------------------------------------------------------------------ 390
    def _calcular_390(self, ejercicio: int) -> calculo390.Resultado390:
        return calculo390.calcular(ejercicio, self.libro.listar(), self.autoliqs.listar("303", ejercicio), self.perfil())

    def calcular_390(self, ejercicio: int) -> dict[str, Any]:
        ej = int(ejercicio)
        res = self._calcular_390(ej)
        out = res.to_dict()
        try:
            out["diseno"] = diseno.seleccionar(Trimestre(ej, 4), self.rutas.disenos, "390").entrada.archivo
        except LookupError as e:
            out["diseno"] = None
            out["bloqueos"].append(str(e))
            out["generable"] = False
        if not self._ultima_comprobacion(f"390-{ej}"):
            out["avisos"].append("No se ha comprobado en los últimos 7 días si hay un diseño nuevo del 390: ejecuta comprobar_diseno_390.")
        p = plazo_303(Trimestre(ej, 4))
        out["plazo"] = {"inicio": p.inicio.isoformat(), "fin": p.fin.isoformat()}
        return out

    def generar_390(self, ejercicio: int) -> dict[str, Any]:
        ej = int(ejercicio)
        perfil = self.perfil()
        res = self._calcular_390(ej)
        if res.bloqueos:
            return {"generado": False, "bloqueos": res.bloqueos, "calculo": res.to_dict()}
        disp = diseno.seleccionar(Trimestre(ej, 4), self.rutas.disenos, "390")
        d = diseno.cargar(disp)
        contenido = fichero390.generar(d, res, perfil)
        leido = fichero390.leer(d, contenido)
        for pag, casillas in res.casillas.items():
            for cas, v in casillas.items():
                campo = fichero.campo(d.paginas[pag], fichero390.ESPEC, f"[{cas}]")
                if leido[pag][f"[{cas}]"] != fichero.formatear(campo, v):
                    raise RuntimeError(f"Verificación interna fallida en la casilla {cas} del 390.")
        carpeta = self.rutas.base / "390" / str(ej)
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = carpeta / fichero390.nombre_fichero(res, perfil)
        ruta.write_bytes(contenido)
        resumen = res.to_dict()
        resumen.update({"diseno": disp.entrada.archivo, "fichero": str(ruta), "generado_en": _ahora()})
        (carpeta / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        planas = {c: v for pag in res.casillas.values() for c, v in pag.items()}
        self.autoliqs.guardar_generada("390", ej, "0A", planas, None, None, str(ruta))
        avisos = list(res.avisos)
        if not self._ultima_comprobacion(f"390-{ej}"):
            avisos.append("No se ha comprobado recientemente si hay un diseño nuevo del 390 (comprobar_diseno_390).")
        return {
            "generado": True,
            "fichero": str(ruta),
            "diseno": disp.entrada.archivo,
            "resultado_liquidacion_anual": resumen["resultado_liquidacion_anual"],
            "casillas": resumen["casillas"],
            "trimestres": res.trimestres,
            "explicacion": res.explicacion,
            "avisos": avisos,
            "siguientes_pasos": PASOS_SEDE_390,
        }

    # ---------------------------------------------------------------- plazos
    def plazos(self, hoy: str | None = None) -> list[dict[str, Any]]:
        d = date.fromisoformat(hoy) if hoy else date.today()
        res = []
        for p in proximos_plazos(d):
            item = {"trimestre": str(p.trimestre), "inicio": p.inicio.isoformat(), "fin": p.fin.isoformat(),
                    "fin_domiciliacion": p.fin_domiciliacion.isoformat(), "abierto": p.inicio <= d <= p.fin}
            if p.trimestre.es_ultimo:
                item["modelo_390"] = (f"En el mismo plazo se presenta el 390 del ejercicio {p.trimestre.ejercicio} "
                                      "(salvo exonerados): calcular_390 / generar_390.")
            res.append(item)
        return res


def _fecha_iso(texto: str) -> str:
    texto = texto.strip()
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", texto)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    return date.fromisoformat(texto[:10]).isoformat()


def _aritmetica_303(cas: dict[str, Any]) -> list[str]:
    """Comprueba las relaciones entre casillas del 303 (las que se hayan indicado)."""
    def c(k: str):
        return cas.get(k, CERO)

    def suma(ks: tuple[str, ...]):
        return sum((c(k) for k in ks), CERO)

    reglas = [
        ("27", suma(("152", "167", "03", "155", "06", "09", "11", "13", "15", "158", "170", "18", "21", "24", "26")),
         "[27] = suma de cuotas devengadas"),
        ("45", suma(("29", "31", "33", "35", "37", "39", "41", "42", "43", "44")), "[45] = suma de deducciones"),
        ("46", c("27") - c("45"), "[46] = [27] − [45]"),
        ("64", c("46") + c("58") + c("76"), "[64] = [46] + [58] + [76]"),
        ("66", redondear((c("64") if "64" in cas else c("46")) * cas.get("65", Decimal("100")) / 100), "[66] = [64] × [65] %"),
        ("69", c("66") + c("77") - c("78") + c("68") + c("108"), "[69] = [66] + [77] − [78] + [68] + [108]"),
        ("71", c("69") - c("70") + c("109") - c("112"), "[71] = [69] − [70] + [109] − [112]"),
    ]
    errores = []
    for casilla, esperado, texto in reglas:
        if casilla in cas and cas[casilla] != esperado and (casilla != "71" or "69" in cas):
            errores.append(f"{texto}: debería ser {formato_es(esperado)} y se indicó {formato_es(cas[casilla])}")
    return errores


FUENTES_PERFIL = [
    "1. El último 303 presentado (justificante PDF): muestra las casillas de identificación que aceptó la AEAT "
    "(casillas sin marcar = NO), el NIF y nombre, la forma de pago y las cuotas a compensar (casillas 87 y 72). Léelo tú.",
    "2. 'Mis datos censales' en la Sede o la última declaración censal (036/037): solo el usuario puede consultarlos.",
    "3. Preguntar al usuario con la pregunta de cada campo. Si no lo sabe y no hay documentos, no lo supongas.",
]

PASOS_SEDE_390 = [
    "Entra en la Sede de la AEAT > IVA > Modelo 390 > 'Presentación (con fichero)' del ejercicio (certificado, Cl@ve o DNIe).",
    "Importa el fichero .390 generado.",
    "Revisa todas las casillas; si algo no está bien, corrígelo aquí y vuelve a generar el fichero.",
    "Valida, firma y envía. Guarda el justificante.",
]

PASOS_SEDE = [
    "Entra en la Sede Electrónica de la AEAT > IVA > Modelo 303 > Presentar (con certificado, Cl@ve o DNIe).",
    "Elige la opción de importar un fichero y selecciona el fichero generado.",
    "Revisa todas las casillas. Si algo no está bien, corrígelo aquí y vuelve a generar el fichero (los datos importados no se editan en la Sede).",
    "Pulsa Validar, después Firmar y enviar.",
    "Guarda el justificante (PDF con el CSV) junto con tus declaraciones anteriores.",
]


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


__all__ = ["Servicio", "campos_factura"]
