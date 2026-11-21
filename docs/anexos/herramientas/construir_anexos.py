# -*- coding: utf-8 -*-
"""
Construye los anexos en Word a partir de los textos de docs/anexos/fuentes/*.md.

    py docs/anexos/herramientas/construir_anexos.py [anexo_3 ...]

Formato de las fuentes (un subconjunto de Markdown):
  titulo: / subtitulo: / encabezado:   datos de la portada (primeras líneas)
  ## Título 1   ### Título 2   #### Título 3
  - viñeta       1. lista numerada      > recuadro de nota
  | tabla |      ![Pie de figura](ruta relativa a docs/anexos)
  ```código```   ===  (salto de página)
Necesita Microsoft Word. Los documentos deben estar cerrados.
"""
import glob
import os
import re
import sys

import pythoncom
import win32com.client as com
from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(AQUI, ".."))
FUENTES = os.path.join(BASE, "fuentes")

NORMAL, H1, H2, H3, TITULO, SUBTITULO, VINETA, NUMERO = -1, -2, -3, -4, -63, -75, -49, -50
AZUL, GRIS, GRIS_CLARO, NOTA = 0x64381F, 0x707070, 0xF2F2F2, 0xF7EBDE   # BGR
ANCHO = 467.0                     # carta con márgenes de 2,5 cm (puntos)
ALTO_MAX = 600.0


def limpiar(t):
    return re.sub(r"\*\*|`", "", t).strip()


def es_tabla(l):
    return l.lstrip().startswith("|")


def celdas(l):
    return [c.strip() for c in l.strip().strip("|").split("|")]


class Documento:
    def __init__(self, word, encabezado):
        self.d = word.Documents.Add()
        s = self.d.PageSetup
        s.PageWidth, s.PageHeight = 612, 792
        s.TopMargin = s.BottomMargin = s.LeftMargin = s.RightMargin = 71
        self.figura = 0
        self.tabla_n = 0
        self._estilos()
        sec = self.d.Sections(1)
        sec.PageSetup.DifferentFirstPageHeaderFooter = True
        enc = sec.Headers(1).Range
        enc.Text = encabezado
        enc.Font.Size, enc.Font.Color = 9, GRIS
        enc.ParagraphFormat.Alignment = 2
        sec.Footers(1).PageNumbers.Add(1)

    def _estilos(self):
        for e, tam, antes, despues in ((NORMAL, 11, 0, 6), (H1, 16, 18, 8), (H2, 13, 14, 6),
                                       (H3, 11.5, 10, 4), (TITULO, 28, 0, 6), (SUBTITULO, 14, 0, 18)):
            st = self.d.Styles(e)
            st.Font.Name, st.Font.Size = "Calibri", tam
            st.ParagraphFormat.SpaceBefore, st.ParagraphFormat.SpaceAfter = antes, despues
            st.LanguageID = 13322
            if e in (H1, H2, H3, TITULO):
                st.Font.Color, st.Font.Bold = AZUL, True
                st.ParagraphFormat.KeepWithNext = True
            if e == SUBTITULO:
                st.Font.Color = GRIS
        self.d.Styles(NORMAL).ParagraphFormat.LineSpacingRule = 0

    def _fin(self):
        n = self.d.Content.End - 1
        return self.d.Range(n, n)

    def _nuevo(self):
        self._fin().InsertParagraphAfter()
        u = self.d.Paragraphs.Last
        u.Style = NORMAL
        u.Range.Font.Reset()
        u.Range.ParagraphFormat.Reset()
        u.Range.ParagraphFormat.Alignment = 0

    def parrafo(self, texto, estilo=NORMAL, alinear=None, sombra=None, tam=None, sangria=None):
        p = self.d.Paragraphs.Last
        p.Style = estilo
        if sangria:        # (izquierda, colgante) en puntos
            p.LeftIndent, p.FirstLineIndent = sangria[0], -sangria[1]
            if sangria[1]:
                p.TabStops.Add(sangria[0])
        for seg in re.split(r"(\*\*.+?\*\*|`.+?`)", texto):
            if not seg:
                continue
            r = self._fin()
            r.Text = re.sub(r"\*\*|`", "", seg)
            r.Font.Reset()
            if seg.startswith("**"):
                r.Bold = True
            elif seg.startswith("`"):
                r.Font.Name, r.Font.Size = "Consolas", 9.5
            if tam:
                r.Font.Size = tam
        if alinear is not None:
            p.Range.ParagraphFormat.Alignment = alinear
        if sombra is not None:
            p.Range.ParagraphFormat.Shading.BackgroundPatternColor = sombra
            for lado in (-1, -2, -3, -4):
                b = p.Range.ParagraphFormat.Borders(lado)
                b.LineStyle, b.Color = 1, 0xC9A27E if sombra == NOTA else 0xD0D0D0
            p.Range.ParagraphFormat.LeftIndent = p.Range.ParagraphFormat.RightIndent = 4
        self._nuevo()

    def codigo(self, lineas):
        for i, l in enumerate(lineas):
            p = self.d.Paragraphs.Last
            r = self._fin()
            r.Text = l if l else " "
            r.Font.Name, r.Font.Size = "Consolas", 9
            f = p.Range.ParagraphFormat
            f.SpaceAfter, f.SpaceBefore = 0, 0
            f.Shading.BackgroundPatternColor = GRIS_CLARO
            f.LeftIndent = 8
            self._nuevo()
        self.d.Paragraphs.Last.Range.ParagraphFormat.SpaceBefore = 6

    def imagen(self, ruta, pie):
        ruta = os.path.abspath(os.path.join(BASE, ruta))
        if not os.path.exists(ruta):
            self.parrafo(f"[Falta la imagen: {os.path.basename(ruta)}]")
            return
        w, h = Image.open(ruta).size
        ancho = min(ANCHO, w * 0.75)
        if ancho * h / w > ALTO_MAX:
            ancho = ALTO_MAX * w / h
        p = self.d.Paragraphs.Last
        p.Range.ParagraphFormat.Alignment = 1
        p.Range.ParagraphFormat.KeepWithNext = True
        forma = self.d.InlineShapes.AddPicture(ruta, False, True, self._fin())
        forma.LockAspectRatio = True
        forma.Width = ancho
        for lado in (-1, -2, -3, -4):
            forma.Borders(lado).LineStyle = 1
            forma.Borders(lado).Color = 0xBFBFBF
        self._nuevo()
        self.figura += 1
        self.parrafo(f"Figura {self.figura}. {pie}", alinear=1, tam=9.5)
        c = self.d.Paragraphs(self.d.Paragraphs.Count - 1).Range
        c.Font.Italic, c.Font.Color = True, GRIS

    def tabla(self, filas):
        cols = max(len(f) for f in filas)
        filas = [f + [""] * (cols - len(f)) for f in filas]
        t = self.d.Tables.Add(self.d.Paragraphs.Last.Range, len(filas), cols)
        t.Borders.Enable = True
        t.Borders.InsideColor = t.Borders.OutsideColor = 0xBFBFBF
        t.Range.Font.Size = 9.5
        t.Range.ParagraphFormat.SpaceAfter = 0
        t.Range.ParagraphFormat.SpaceBefore = 0
        t.TopPadding = t.BottomPadding = 2.5
        t.LeftPadding = t.RightPadding = 4
        largos = [max(min(len(limpiar(f[c])), 60) for f in filas) + 6 for c in range(cols)]
        for c in range(cols):
            t.Columns(c + 1).Width = ANCHO * largos[c] / sum(largos)
        for i, fila in enumerate(filas, 1):
            for j, v in enumerate(fila, 1):
                celda = t.Cell(i, j).Range
                celda.Text = limpiar(v)
                if v.strip().startswith("**"):
                    celda.Bold = True
        cab = t.Rows(1)
        cab.HeadingFormat = True
        cab.Range.Bold = True
        cab.Range.Font.Color = 0xFFFFFF
        cab.Shading.BackgroundPatternColor = AZUL
        t.Rows.AllowBreakAcrossPages = False
        self._nuevo()
        self.d.Paragraphs.Last.Range.ParagraphFormat.SpaceBefore = 6

    def salto(self):
        self._fin().InsertBreak(7)

    def indice(self):
        self.parrafo("Índice", H1)
        self.d.Paragraphs(self.d.Paragraphs.Count - 1).Style = NORMAL
        p = self.d.Paragraphs(self.d.Paragraphs.Count - 1).Range
        p.Font.Size, p.Font.Bold, p.Font.Color = 16, True, AZUL
        self.toc = self.d.TablesOfContents.Add(self._fin(), True, 1, 2)
        self._nuevo()
        self.salto()


def construir(word, fuente):
    lineas = open(fuente, encoding="utf-8").read().splitlines()
    meta = {}
    while lineas and re.match(r"^(titulo|subtitulo|encabezado|archivo):", lineas[0]):
        k, v = lineas.pop(0).split(":", 1)
        meta[k] = v.strip()
    doc = Documento(word, meta.get("encabezado", ""))
    # portada
    for _ in range(6):
        doc._nuevo()
    doc.parrafo(meta.get("titulo", ""), TITULO)
    doc.parrafo(meta.get("subtitulo", ""), SUBTITULO)
    for l in ("Proyecto: Umbral Guardian — control de accesos con visión artificial",
              "Autor: Matías Tejada", "INACAP", "Noviembre de 2026"):
        doc.parrafo(l, tam=12)
    doc.salto()
    doc.indice()

    i = 0
    en_lista = False
    numero = 0
    while i < len(lineas):
        l = lineas[i]
        s = l.strip()
        # un bloque de código o un párrafo con sangría no cortan la lista numerada
        if s and not re.match(r"(- |\d+\. )", s) and not s.startswith("```") \
                and not (en_lista and l.startswith("   ")):
            en_lista = False
        if not s:
            i += 1
        elif s == "===":
            doc.salto()
            i += 1
        elif s.startswith("```"):
            bloque = []
            i += 1
            while i < len(lineas) and not lineas[i].strip().startswith("```"):
                bloque.append(lineas[i].rstrip())
                i += 1
            doc.codigo(bloque)
            i += 1
        elif s.startswith("#### "):
            doc.parrafo(s[5:], H3)
            i += 1
        elif s.startswith("### "):
            doc.parrafo(s[4:], H2)
            i += 1
        elif s.startswith("## "):
            doc.parrafo(s[3:], H1)
            i += 1
        elif m := re.match(r"!\[(.*)\]\((.+)\)", s):
            doc.imagen(m.group(2), m.group(1))
            i += 1
        elif es_tabla(l):
            filas = []
            while i < len(lineas) and es_tabla(lineas[i]):
                if not re.fullmatch(r"[\s|:\-]+", lineas[i]):
                    filas.append(celdas(lineas[i]))
                i += 1
            doc.tabla(filas)
        elif s.startswith("> "):
            texto = [s[2:]]
            i += 1
            while i < len(lineas) and lineas[i].strip().startswith(">"):
                texto.append(lineas[i].strip()[1:].strip())
                i += 1
            doc.parrafo(" ".join(texto), sombra=NOTA)
        else:
            m = re.match(r"(- |\d+\. )(.*)", s)
            texto = [m.group(2) if m else s]
            i += 1
            while i < len(lineas) and lineas[i].startswith("  ") and lineas[i].strip() \
                    and not re.match(r"\s*(- |\d+\. )", lineas[i]):
                texto.append(lineas[i].strip())
                i += 1
            sangria = 18 if l.startswith("   ") else 0
            if m and m.group(1) != "- ":
                # numeración escrita como texto: cada lista parte en 1 sin depender de Word
                numero = numero + 1 if en_lista else 1
                doc.parrafo(f"{numero}.\t" + " ".join(texto), NORMAL, sangria=(sangria + 18, 18))
            elif m:
                doc.parrafo(" ".join(texto), VINETA)
                if sangria:
                    doc.d.Paragraphs(doc.d.Paragraphs.Count - 1).LeftIndent += 18
            else:
                doc.parrafo(" ".join(texto), NORMAL,
                            sangria=(18, 0) if en_lista and l.startswith("   ") else None)
            en_lista = bool(m) or (en_lista and l.startswith("   "))
    doc.d.Paragraphs.Last.Range.Delete()
    doc.toc.Update()
    doc.d.BuiltInDocumentProperties("Title").Value = meta.get("titulo", "")
    doc.d.BuiltInDocumentProperties("Author").Value = "Matías Tejada"
    salida = os.path.join(BASE, meta["archivo"])
    doc.d.SaveAs2(salida, 16)
    pdf = os.path.join(os.environ.get("TEMP", BASE), os.path.basename(salida)[:-5] + ".pdf")
    doc.d.SaveAs2(pdf, 17)
    paginas = doc.d.ComputeStatistics(2)
    doc.d.Close(0)
    print(f"{meta['archivo']}: {paginas} páginas, {doc.figura} figuras | revisión: {pdf}")


def main():
    pedidos = sys.argv[1:]
    pythoncom.CoInitialize()
    word = com.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        for f in sorted(glob.glob(os.path.join(FUENTES, "*.md"))):
            if not pedidos or any(p in f for p in pedidos):
                construir(word, f)
    finally:
        word.Quit()


if __name__ == "__main__":
    main()
