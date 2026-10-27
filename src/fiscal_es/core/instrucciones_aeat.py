"""Consulta de las instrucciones oficiales del modelo 303 publicadas por la AEAT.

La ficha del procedimiento (G414) enlaza unas "Instrucciones AAAA" por ejercicio.
Cada ejercicio puede tener varias subpáginas (p. ej. 2026: "01-1T" y "02 a 12 y 2T a 4T").
Aquí se descargan, se trocean en bloques con su sección y se buscan por palabras o
por número de casilla, para que el agente responda dudas citando el texto oficial
en lugar de inventarlo.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from .aeat import get_cacheado

PAGINA_PROCEDIMIENTO = "https://sede.agenciatributaria.gob.es/Sede/procedimientoini/G414.shtml"
# Ficha del procedimiento de cada modelo: enlaza las "Instrucciones AAAA" (HTML en el 303, PDF en el 390).
PROCEDIMIENTOS = {
    "303": PAGINA_PROCEDIMIENTO,
    "390": "https://sede.agenciatributaria.gob.es/Sede/procedimientoini/G412.shtml",
}

_BLOQUE = {"p", "li", "td", "th", "dd", "dt", "caption"}
_TITULO = {"h1", "h2", "h3", "h4", "h5", "h6"}
_IGNORAR = {"script", "style", "nav", "header", "footer", "noscript", "form"}


@dataclass
class Bloque:
    seccion: str
    texto: str


@dataclass
class Pagina:
    titulo: str
    url: str
    bloques: list[Bloque] = field(default_factory=list)


class _Extractor(HTMLParser):
    """Convierte el HTML en bloques de texto con la sección (títulos) en la que están."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.titulos: list[tuple[int, str]] = []
        self.bloques: list[Bloque] = []
        self._buf: list[str] = []
        self._en: str | None = None
        self._ignorar = 0
        self._en_main = False
        self.titulo_h2: str | None = None

    def _seccion(self) -> str:
        return " > ".join(t for _, t in self.titulos)

    def _cerrar(self) -> None:
        texto = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        self._buf = []
        if not texto or self._en is None:
            return
        if self._en in _TITULO:
            nivel = int(self._en[1])
            self.titulos = [(n, t) for n, t in self.titulos if n < nivel] + [(nivel, texto)]
            if nivel == 2 and self.titulo_h2 is None:
                self.titulo_h2 = texto
        elif len(texto) > 2:
            self.bloques.append(Bloque(self._seccion(), texto))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _IGNORAR:
            self._ignorar += 1
            return
        if tag == "main":
            self._en_main = True
        if tag in _TITULO or tag in _BLOQUE:
            self._cerrar()
            self._en = tag
        elif tag == "br":
            self._buf.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _IGNORAR:
            self._ignorar = max(0, self._ignorar - 1)
            return
        if tag in _TITULO or tag in _BLOQUE:
            self._cerrar()
            self._en = None

    def handle_data(self, data: str) -> None:
        if self._ignorar:
            return
        if self._en is None:
            # Texto suelto dentro de divs: se trata como un párrafo propio.
            if data.strip():
                self._en = "p"
                self._buf.append(data)
            return
        self._buf.append(data)


def extraer(html_texto: str) -> tuple[str | None, list[Bloque]]:
    ex = _Extractor()
    ex.feed(html_texto)
    ex._cerrar()
    return ex.titulo_h2, ex.bloques


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def indice_ejercicios(cache: Path | None, modelo: str = "303") -> dict[int, str]:
    """{ejercicio: url} a partir de los enlaces 'Instrucciones AAAA' de la ficha del procedimiento."""
    ficha = PROCEDIMIENTOS[modelo]
    texto = get_cacheado(ficha, cache).decode("utf-8", errors="replace")
    res: dict[int, str] = {}
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>\s*Instrucciones\s+(\d{4})\s*<', texto, re.I):
        res[int(m.group(2))] = urljoin(ficha, html.unescape(m.group(1)))
    return res


# En los PDF: títulos de apartado ("7. Resultado de la liquidación anual", "9.1. Períodos…")
# y párrafos que empiezan por casilla(s) ("95 Total resultados…", "21 a 26, 716 a 719 …").
_PDF_TITULO = re.compile(r"^\d{1,2}(?:\.\d{1,2})*\.\s+[A-ZÁÉÍÓÚÑ]")
_PDF_PARRAFO = re.compile(r"^(?:\d{1,3}(?:\s*(?:,|y|a)\s*\d{1,3})*\s+[A-ZÁÉÍÓÚÑ]|-\s*Casillas?\b|Casillas?\s+\d|[-•]\s)")


def extraer_pdf(datos: bytes) -> list[Bloque]:
    """Bloques de texto de un PDF de instrucciones, con el apartado en el que están."""
    import io

    from pypdf import PdfReader

    try:
        lector = PdfReader(io.BytesIO(datos))
        lineas = [l.strip() for p in lector.pages for l in (p.extract_text() or "").splitlines()]
    except Exception:
        return []
    bloques: list[Bloque] = []
    seccion = ""
    actual: list[str] = []

    def cerrar() -> None:
        texto = re.sub(r"\s+", " ", " ".join(actual)).strip()
        if len(texto) > 2:
            bloques.append(Bloque(seccion, texto))
        actual.clear()

    for l in lineas:
        if not l or re.fullmatch(r"\d{1,3}", l):  # líneas vacías y números de página
            continue
        if _PDF_TITULO.match(l) and len(l) < 100:
            cerrar()
            seccion = l
            continue
        if _PDF_PARRAFO.match(l):
            cerrar()
        actual.append(l)
        if l.endswith(".") and len(l) < 60:
            cerrar()
    cerrar()
    return bloques


def paginas_ejercicio(ejercicio: int, cache: Path | None, modelo: str = "303") -> list[Pagina]:
    indice = indice_ejercicios(cache, modelo)
    if ejercicio not in indice:
        disponibles = ", ".join(str(a) for a in sorted(indice)) or "ninguno"
        raise LookupError(
            f"La AEAT no publica todavía instrucciones del {modelo} para {ejercicio} (disponibles: {disponibles})."
        )
    url = indice[ejercicio]
    datos = get_cacheado(url, cache)
    if url.lower().endswith(".pdf") or datos[:4] == b"%PDF":
        return [Pagina(f"Instrucciones del modelo {modelo} - {ejercicio}", url, extraer_pdf(datos))]
    texto = datos.decode("utf-8", errors="replace")
    prefijo = url[: -len(".html")] + "/" if url.endswith(".html") else url
    subpaginas: dict[str, str] = {}
    for m in re.finditer(r'<a[^>]+href="([^"]+\.html)"[^>]*>([^<]*)<', texto, re.I):
        href = urljoin(url, html.unescape(m.group(1)))
        titulo = re.sub(r"\s+", " ", html.unescape(m.group(2))).strip()
        if href.startswith(prefijo) and titulo:
            subpaginas.setdefault(href, titulo)
    titulo, bloques = extraer(texto)
    paginas = [Pagina(titulo or f"Instrucciones {ejercicio}", url, bloques)]
    for href, tit in subpaginas.items():
        t, b = extraer(get_cacheado(href, cache).decode("utf-8", errors="replace"))
        paginas.append(Pagina(t or tit, href, b))
    return paginas


def _aplica_periodo(titulo: str, periodo: str | None) -> bool:
    if not periodo:
        return True
    p = periodo.upper()
    t = titulo.upper()
    if p == "1T":
        return bool(re.search(r"\b1T\b|01-1T", t)) or not re.search(r"\dT", t)
    if re.search(r"2T A 4T", t):
        return p in ("2T", "3T", "4T")
    return p in t or not re.search(r"\dT", t)


def _casillas_consulta(consulta: str) -> list[int]:
    return [int(n) for n in re.findall(r"(?:casillas?\s*|\[)\s*(\d{1,3})\]?", consulta, re.I)]


def _cubre_casilla(texto: str, n: int) -> float:
    """Puntuación si el bloque se refiere a la casilla n.

    En las instrucciones las casillas aparecen como etiquetas sueltas en tablas
    ('28 a 39', '01, 02 y 03', '28 y siguientes'), al principio de un párrafo
    ('87 Cuotas a compensar...') o citadas en el texto ('[28]', 'casilla 28').
    """
    t = _norm(texto).strip()
    if len(t) <= 60 and re.fullmatch(r"[\d\s,.ya\-–]+(siguientes)?", t):
        for a, b in re.findall(r"(\d+)\s*(?:a|-|–)\s*(\d+)", t):
            if int(a) <= n <= int(b):
                return 8
        if "siguientes" in t:
            # 'NN y siguientes' es demasiado genérico: solo suma si hay otras coincidencias.
            m = re.match(r"(\d+)", t)
            return 0.5 if m and n >= int(m.group(1)) else 0
        return 8 if n in {int(x) for x in re.findall(r"\d+", t)} else 0
    # Párrafo que empieza por el número de casilla: "87 Cuotas a compensar de...", "Casilla 662 Esta…".
    if re.match(rf"\s*(?:-\s*)?(?:Casillas?\s+)?\[?0*{n}\]?\s+[^\W\d_]", texto, re.I):
        return 8
    if re.search(rf"\[\s*0*{n}\s*\]|casillas?\s+(?:\d+\s*(?:,|y|a)\s*)*0*{n}\b", texto, re.I):
        return 5
    return 0


_VACIAS = {"de", "la", "el", "los", "las", "y", "o", "en", "que", "del", "por", "para", "con", "un", "una",
           "se", "al", "es", "a", "lo", "como", "su", "sus", "si", "no", "me", "mi", "casilla", "casillas"}


RELEVANCIA_MINIMA = 1.0


def buscar(paginas: list[Pagina], consulta: str, periodo: str | None = None, max_resultados: int = 6) -> list[dict[str, Any]]:
    """Bloques más relevantes para la consulta, con el bloque anterior y el siguiente como contexto."""
    terminos = [t for t in re.findall(r"\w+", _norm(consulta)) if t not in _VACIAS and len(t) > 2]
    casillas = _casillas_consulta(consulta)
    candidatos: list[tuple[float, int, int, Pagina, bool]] = []
    for pi, pag in enumerate(paginas):
        if not _aplica_periodo(pag.titulo, periodo):
            continue
        for bi, b in enumerate(pag.bloques):
            texto_n = _norm(b.texto)
            seccion_n = _norm(b.seccion)
            puntos = 0.0
            etiqueta = False
            for n in casillas:
                c = _cubre_casilla(b.texto, n)
                puntos += c
                etiqueta = etiqueta or c >= 8
            for t in terminos:
                n = texto_n.count(t)
                puntos += min(n, 3) + (1 if t in seccion_n else 0)
            if terminos and not etiqueta:
                cubiertos = sum(1 for t in terminos if t in texto_n or t in seccion_n)
                puntos *= cubiertos / len(terminos)
            if puntos >= RELEVANCIA_MINIMA:
                candidatos.append((puntos, pi, bi, pag, etiqueta))
    candidatos.sort(key=lambda c: (-c[0], c[1], c[2]))
    res: list[dict[str, Any]] = []
    usados: set[tuple[int, int]] = set()
    for puntos, pi, bi, pag, etiqueta in candidatos:
        if len(res) >= max_resultados:
            break
        if (pi, bi) in usados:
            continue
        # Una etiqueta de casilla va seguida de su explicación: se toman los bloques siguientes.
        rango = range(bi, min(len(pag.bloques), bi + 4)) if etiqueta else range(max(0, bi - 1), min(len(pag.bloques), bi + 2))
        usados.update((pi, i) for i in rango)
        res.append({
            "pagina": pag.titulo,
            "url": pag.url,
            "seccion": pag.bloques[bi].seccion,
            "texto": "\n".join(pag.bloques[i].texto for i in rango),
            "relevancia": round(puntos, 2),
        })
    return res


def indice_secciones(paginas: list[Pagina], periodo: str | None = None) -> list[dict[str, Any]]:
    out = []
    for pag in paginas:
        if not _aplica_periodo(pag.titulo, periodo):
            continue
        secciones: list[str] = []
        for b in pag.bloques:
            if b.seccion and b.seccion not in secciones:
                secciones.append(b.seccion)
        out.append({"pagina": pag.titulo, "url": pag.url, "secciones": secciones})
    return out
