"""Modifica del testo esistente e inserimento di testo nuovo.

Un PDF non contiene paragrafi ma caratteri posizionati. Per modificare un blocco:
1. si leggono righe e "span" (tratti con lo stesso font, corpo e colore);
2. si ricostruiscono i paragrafi (righe unite se il testo prosegue);
3. dopo la modifica si cancellano i caratteri originali (redazione solo del testo,
   senza toccare immagini e grafica) e si riscrive il testo con un'impaginazione
   propria (a capo, allineamento, interlinea), incorporando il font scelto.
   Non si usa il motore HTML di MuPDF perché crea legature tipografiche che poi,
   copiando il testo, diventano caratteri sbagliati.

Font: se il font incorporato nel PDF contiene tutti i caratteri del testo nuovo
si riusa quello (aspetto identico); altrimenti il font di Windows con lo stesso
nome; altrimenti Arial, segnalandolo nelle avvertenze.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field

import pymupdf

from .. import fonts
from .common import DICT_FLAGS, apply_internal_redactions, int_to_hex, search_page

ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT, ALIGN_JUSTIFY = 0, 1, 2, 3
_ALIGN_CSS = {0: "left", 1: "center", 2: "right", 3: "justify"}


@dataclass
class Run:
    text: str
    family: str = "Arial"
    size: float = 11.0
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str = "#000000"


@dataclass
class Para:
    runs: list[Run] = field(default_factory=list)
    align: int = ALIGN_LEFT
    line_height: float = 1.2

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


@dataclass
class TextBlock:
    """Blocco di testo di una pagina, in coordinate PDF non ruotate."""
    index: int
    rect: pymupdf.Rect
    line_rects: list[pymupdf.Rect]
    paras: list[Para]
    embedded: dict[str, int]       # famiglia -> xref del font incorporato (TrueType/OpenType)
    horizontal: bool
    dir: tuple[float, float]

    @property
    def text(self) -> str:
        return "\n".join(p.text for p in self.paras)


# ------------------------------------------------------------------ lettura
def _embedded_fonts(page: pymupdf.Page) -> dict[str, tuple[int, str]]:
    """basefont -> (xref, estensione)"""
    out = {}
    try:
        for f in page.get_fonts(full=True):
            xref, ext, _type, basefont = f[0], f[1], f[2], f[3]
            out[basefont] = (xref, ext)
            if "+" in basefont:
                out[basefont.split("+", 1)[1]] = (xref, ext)
    except Exception:
        pass
    return out


def _span_run(span: dict) -> Run:
    name = span.get("font", "")
    base, nbold, nital = fonts.clean_pdf_font_name(name)
    flags = span.get("flags", 0)
    bold = bool(flags & 16) or nbold
    italic = bool(flags & 2) or nital
    fam = fonts.find_family(name) or base or fonts.FALLBACK_FAMILY
    size = round(span.get("size", 11) * 2) / 2
    return Run(span.get("text", "").replace("\xa0", " "), fam, size, bold, italic, False, int_to_hex(span.get("color", 0)))


def _detect_align(block_rect, line_rects) -> int:
    if len(line_rects) < 2:
        return ALIGN_LEFT
    w = block_rect.width or 1
    lefts = [r.x0 - block_rect.x0 for r in line_rects]
    rights = [block_rect.x1 - r.x1 for r in line_rects]
    tol = max(2.0, w * 0.02)
    if all(abs(l - r) < tol for l, r in zip(lefts, rights)) and max(lefts) > tol:
        return ALIGN_CENTER
    if all(r < tol for r in rights) and max(lefts) > tol:
        return ALIGN_RIGHT
    if len(line_rects) >= 3 and all(l < tol and r < tol for l, r in zip(lefts[:-1], rights[:-1])):
        return ALIGN_JUSTIFY
    return ALIGN_LEFT


def read_blocks(page: pymupdf.Page, text_dict: dict | None = None) -> list[TextBlock]:
    d = text_dict or page.get_text("dict", flags=DICT_FLAGS)
    emb = _embedded_fonts(page)
    rot = page.rotation_matrix
    blocks = []
    for bi, b in enumerate(d.get("blocks", [])):
        if b.get("type") != 0 or not b.get("lines"):
            continue
        lines = [l for l in b["lines"] if any(s.get("text", "").strip() for s in l["spans"])]
        if not lines:
            continue
        brect = pymupdf.Rect(b["bbox"])
        line_rects = [pymupdf.Rect(l["bbox"]) for l in lines]
        dx, dy = lines[0].get("dir", (1, 0))
        # direzione della riga come appare a schermo
        vx = dx * rot.a + dy * rot.c
        vy = dx * rot.b + dy * rot.d
        horizontal = abs(vy) < 0.01 and vx > 0
        paras: list[Para] = []
        cur: Para | None = None
        sizes = []
        prev_line = None
        emb_map: dict[str, int] = {}
        for li, l in enumerate(lines):
            runs = []
            for s in l["spans"]:
                if not s.get("text"):
                    continue
                r = _span_run(s)
                runs.append(r)
                sizes.append(r.size)
                key = s.get("font", "")
                e = emb.get(key)
                if e and e[1] in ("ttf", "otf") and r.family not in emb_map:
                    emb_map[r.family + ("|b" if r.bold else "") + ("|i" if r.italic else "")] = e[0]
            if not runs:
                continue
            lr = pymupdf.Rect(l["bbox"])
            new_para = cur is None
            if prev_line is not None and not new_para:
                short = prev_line.x1 < brect.x1 - max(brect.width * 0.2, 12)
                gap = lr.y0 - prev_line.y1
                big_gap = gap > (sizes[-1] if sizes else 11) * 0.9
                new_para = short or big_gap
            if new_para:
                cur = Para(runs=[])
                paras.append(cur)
            else:
                last = cur.runs[-1]
                if last.text.endswith("-") and runs[0].text[:1].islower():
                    last.text = last.text[:-1]
                elif not last.text.endswith(" ") and not runs[0].text.startswith(" "):
                    last.text += " "
            for r in runs:
                if cur.runs and _same_style(cur.runs[-1], r):
                    cur.runs[-1].text += r.text
                else:
                    cur.runs.append(r)
            prev_line = lr
        # interlinea media
        if len(lines) > 1:
            ys = [l["spans"][0]["origin"][1] for l in lines if l["spans"]]
            gaps = [b2 - a2 for a2, b2 in zip(ys, ys[1:]) if b2 > a2]
            avg_size = sum(sizes) / len(sizes) if sizes else 11
            if gaps and avg_size:
                lh = max(1.0, min(2.5, (sum(gaps) / len(gaps)) / avg_size))
                for p in paras:
                    p.line_height = round(lh, 2)
        align = _detect_align(brect, line_rects)
        for p in paras:
            p.align = align
            p.runs[-1].text = p.runs[-1].text.rstrip()
        blocks.append(TextBlock(bi, brect, line_rects, paras, emb_map, horizontal, (dx, dy)))
    return blocks


def _same_style(a: Run, b: Run) -> bool:
    return (a.family, a.size, a.bold, a.italic, a.underline, a.color) == (b.family, b.size, b.bold, b.italic, b.underline, b.color)


def block_at(blocks: list[TextBlock], point: pymupdf.Point, margin: float = 2) -> TextBlock | None:
    best = None
    for b in blocks:
        r = pymupdf.Rect(b.rect)
        r.x0 -= margin; r.y0 -= margin; r.x1 += margin; r.y1 += margin
        if point in r:
            if best is None or b.rect.get_area() < best.rect.get_area():
                best = b
    return best


# --------------------------------------------------------------- scrittura
class FontResolver:
    """Sceglie il file di font per ogni tratto di testo e lo registra sulla pagina."""

    def __init__(self, page: pymupdf.Page, embedded: dict[str, int] | None = None):
        self.page = page
        self.doc = page.parent
        self.embedded = embedded or {}
        self.dir = tempfile.mkdtemp(prefix="editra_fonts_")
        self.warnings: list[str] = []
        self._emb: dict[int, tuple | None] = {}
        self._sys: dict[str, pymupdf.Font] = {}
        self._registered: set[str] = set()

    def cleanup(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def _emb_font(self, xref: int):
        if xref not in self._emb:
            try:
                name, ext, _t, buf = self.doc.extract_font(xref)
                path = os.path.join(self.dir, f"emb{xref}.{ext}")
                with open(path, "wb") as fh:
                    fh.write(buf)
                self._emb[xref] = (pymupdf.Font(fontfile=path), path)
            except Exception:
                self._emb[xref] = None
        return self._emb[xref]

    def resolve(self, run: Run) -> tuple[str, pymupdf.Font, bool, bool]:
        """(nome registrato sulla pagina, font per le misure, grassetto finto, corsivo finto)."""
        chars = {c for c in run.text if not c.isspace()}
        key = run.family + ("|b" if run.bold else "") + ("|i" if run.italic else "")
        xref = self.embedded.get(key)
        if xref:
            e = self._emb_font(xref)
            if e is not None and all(e[0].has_glyph(ord(c)) for c in chars):
                return self._register(f"E{xref}", e[1]), e[0], False, False
        family = run.family
        path = fonts.font_file(family, run.bold, run.italic)
        if not path:
            if family != fonts.FALLBACK_FAMILY:
                w = f"Font «{family}» non disponibile: usato {fonts.FALLBACK_FAMILY}"
                if w not in self.warnings:
                    self.warnings.append(w)
            family = fonts.FALLBACK_FAMILY
            path = fonts.font_file(family, run.bold, run.italic)
        if not path:
            name = "hebo" if run.bold else "helv"
            return name, pymupdf.Font(name), False, run.italic
        font = self._sys.get(path)
        if font is None:
            font = self._sys[path] = pymupdf.Font(fontfile=path)
        files = fonts.system_fonts().get(family) or {}
        real = next((k for k, v in files.items() if v == path), "r")
        alias = "S" + re.sub(r"[^A-Za-z0-9]", "", os.path.basename(path))[:24]
        return self._register(alias, path), font, run.bold and "b" not in real, run.italic and "i" not in real

    def _register(self, alias: str, path: str) -> str:
        if alias not in self._registered:
            self.page.insert_font(fontname=alias, fontfile=path)
            self._registered.add(alias)
        return alias


def dir_to_rotate(d) -> int:
    """Direzione della riga (coordinate PDF) -> parametro rotate di insert_text."""
    dx, dy = d
    if abs(dx) >= abs(dy):
        return 0 if dx > 0 else 180
    return 90 if dy < 0 else 270


def upright_rotate(page: pymupdf.Page) -> int:
    """rotate per un testo nuovo che appaia dritto sulla pagina come è mostrata."""
    return page.rotation % 360


class _Mapper:
    """Coordinate locali (x lungo la riga, y verso le righe successive) -> coordinate PDF."""

    def __init__(self, rect: pymupdf.Rect, rotate: int):
        self.r = rect
        self.rot = rotate
        self.width = rect.width if rotate in (0, 180) else rect.height

    def pt(self, x: float, y: float) -> pymupdf.Point:
        r = self.r
        if self.rot == 0:
            return pymupdf.Point(r.x0 + x, r.y0 + y)
        if self.rot == 90:
            return pymupdf.Point(r.x0 + y, r.y1 - x)
        if self.rot == 180:
            return pymupdf.Point(r.x1 - x, r.y1 - y)
        return pymupdf.Point(r.x1 - y, r.y0 + x)

    def rect(self, x0, y0, x1, y1) -> pymupdf.Rect:
        return pymupdf.Rect(self.pt(x0, y0), self.pt(x1, y1)).normalize()


_TOKEN = re.compile(r"\S+\s*|\s+")


def _layout(paras: list[Para], res: FontResolver, width: float):
    """Divide i paragrafi in righe: (pezzi, larghezza, passo, ascesa, allineamento, ultima del paragrafo).

    Un pezzo è (run, nome font, font, grassetto finto, corsivo finto, testo).
    """
    lines = []
    for p in paras:
        tokens = []
        for r in p.runs:
            if not r.text:
                continue
            alias, font, sb, si = res.resolve(r)
            for t in _TOKEN.findall(r.text.replace("\n", " ")):
                tokens.append((r, alias, font, sb, si, t))
        if not any(t[5].strip() for t in tokens):
            size = max((r.size for r in p.runs), default=11)
            lines.append(([], 0.0, size * p.line_height, size * 0.8, p.align, True))
            continue
        para_lines = []
        cur, cur_w = [], 0.0
        for tok in tokens:
            r, alias, font, sb, si, t = tok
            w_full = font.text_length(t, fontsize=r.size)
            w_word = font.text_length(t.rstrip(), fontsize=r.size)
            if cur and cur_w + w_word > width + 0.01:
                para_lines.append(cur)
                cur, cur_w = [], 0.0
                if not t.strip():
                    continue
            if not cur and w_word > width:
                # parola più lunga della riga: si spezza per caratteri
                piece = ""
                for ch in t:
                    if piece and font.text_length(piece + ch, fontsize=r.size) > width:
                        para_lines.append([(r, alias, font, sb, si, piece)])
                        piece = ""
                    piece += ch
                cur = [(r, alias, font, sb, si, piece)]
                cur_w = font.text_length(piece, fontsize=r.size)
                continue
            cur.append(tok)
            cur_w += w_full
        if cur:
            para_lines.append(cur)
        for k, items in enumerate(para_lines):
            size = max(it[0].size for it in items)
            asc = max(it[0].size * (it[2].ascender or 0.8) for it in items)
            w = sum(it[2].text_length(it[5], fontsize=it[0].size) for it in items[:-1])
            w += items[-1][2].text_length(items[-1][5].rstrip(), fontsize=items[-1][0].size)
            lines.append((items, w, size * p.line_height, asc, p.align, k == len(para_lines) - 1))
    return lines


def insert_paras(page: pymupdf.Page, rect: pymupdf.Rect, paras: list[Para],
                 embedded: dict[str, int] | None = None, grow: bool = True,
                 rotate: int | None = None) -> tuple[pymupdf.Rect, list[str]]:
    """Scrive i paragrafi nel rettangolo (coordinate PDF), andando a capo dove serve.

    Il testo usa la larghezza del rettangolo; se è più lungo prosegue verso il basso.
    Niente legature tipografiche: il testo resta ricercabile e copiabile carattere per carattere.
    Ritorna il rettangolo occupato e le avvertenze.
    """
    if rotate is None:
        rotate = upright_rotate(page)
    rect = pymupdf.Rect(rect)
    mp = _Mapper(rect, rotate)
    res = FontResolver(page, embedded)
    used = pymupdf.Rect()
    try:
        lines = _layout(paras, res, max(mp.width, 5))
        baseline = None
        for items, w, pitch, asc, align, last in lines:
            baseline = asc if baseline is None else baseline + pitch
            if not items:
                continue
            extra = mp.width - w
            x = extra / 2 if align == ALIGN_CENTER else extra if align == ALIGN_RIGHT else 0.0
            x = max(0.0, x)
            gaps = sum(1 for it in items[:-1] if it[5] != it[5].rstrip())
            per_gap = extra / gaps if align == ALIGN_JUSTIFY and not last and gaps and extra > 0 else 0.0
            # pezzi consecutivi con lo stesso stile in un'unica scrittura (se non si giustifica)
            groups: list[list] = []
            for it in items:
                if groups and not per_gap and groups[-1][0] is it[0]:
                    groups[-1][5] += it[5]
                else:
                    groups.append(list(it))
            for gi, (r, alias, font, sb, si, text) in enumerate(groups):
                draw = text.rstrip() if gi == len(groups) - 1 else text
                adv = font.text_length(draw, fontsize=r.size)
                ink = font.text_length(draw.rstrip(), fontsize=r.size)
                if draw.strip():
                    origin = mp.pt(x, baseline)
                    rgb = _rgb(r.color)
                    kw = dict(fontsize=r.size, fontname=alias, color=rgb, rotate=rotate)
                    if sb:
                        kw.update(render_mode=2, border_width=0.035, fill=rgb)
                    if si:
                        kw["morph"] = (origin, _shear(rotate))
                    page.insert_text(origin, draw, **kw)
                    if r.underline:
                        page.draw_line(mp.pt(x, baseline + r.size * 0.12), mp.pt(x + ink, baseline + r.size * 0.12),
                                       color=rgb, width=max(0.5, r.size * 0.06))
                    used |= mp.rect(x, baseline - asc, x + ink, baseline + r.size * 0.25)
                x += adv
                if per_gap and text != text.rstrip():
                    x += per_gap
        return (used if not used.is_empty else rect), res.warnings
    finally:
        res.cleanup()


def _rgb(hexcolor: str):
    h = (hexcolor or "#000000").lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _shear(rotate: int) -> pymupdf.Matrix:
    """Inclinazione del corsivo finto, nella direzione della riga."""
    m = pymupdf.Matrix(1, 0, -0.2, 1, 0, 0)
    if rotate:
        r = pymupdf.Matrix(-rotate)
        m = ~r * m * r
    return m


def replace_block(page: pymupdf.Page, block: TextBlock, paras: list[Para]) -> list[str]:
    """Sostituisce il testo di un blocco con i paragrafi nuovi."""
    remove = []
    for lr in block.line_rects:
        h = lr.height
        remove.append(pymupdf.Rect(lr.x0 + 0.3, lr.y0 + h * 0.3, lr.x1 - 0.3, lr.y1 - h * 0.3))
    apply_internal_redactions(page, remove, text=True)
    if not any(p.text.strip() for p in paras):
        return []
    r = pymupdf.Rect(block.rect)
    # un piccolo margine evita a-capo dovuti a metriche leggermente diverse
    rot = dir_to_rotate(block.dir)
    if rot in (0, 180):
        r.x1 += max(2.0, r.width * 0.02)
    else:
        r.y1 += max(2.0, r.height * 0.02)
    _, warnings = insert_paras(page, r, paras, block.embedded, rotate=rot)
    return warnings


def delete_block(page: pymupdf.Page, block: TextBlock) -> None:
    replace_block(page, block, [])


def default_box_rect(page: pymupdf.Page, point: pymupdf.Point, width: float = 220, height: float = 40) -> pymupdf.Rect:
    """Rettangolo per un testo nuovo a partire da un clic (coordinate PDF)."""
    r = pymupdf.Rect(point.x, point.y, point.x + width, point.y + height)
    return r & page.mediabox if page.rotation == 0 else r


# --------------------------------------------------------- trova/sostituisci
def find_replace(doc: pymupdf.Document, needle: str, replacement: str, pages=None,
                 match_case: bool = False) -> tuple[int, list[str]]:
    """Sostituisce un testo riga per riga mantenendo font, corpo e colore.

    Ritorna (numero di sostituzioni, avvertenze).
    """
    count = 0
    warnings: list[str] = []
    flags = 0 if match_case else re.IGNORECASE
    pat = re.compile(re.escape(needle), flags)
    for pno in (pages if pages is not None else range(doc.page_count)):
        page = doc[pno]
        if not search_page(page, needle):
            continue
        d = page.get_text("dict", flags=DICT_FLAGS)
        emb = _embedded_fonts(page)
        todo = []
        for b in d["blocks"]:
            if b.get("type") != 0:
                continue
            for l in b["lines"]:
                line_text = "".join(s["text"] for s in l["spans"])
                if not pat.search(line_text):
                    continue
                todo.append(l)
        for l in todo:
            runs = []
            emb_map = {}
            for s in l["spans"]:
                r = _span_run(s)
                n = len(pat.findall(r.text))
                if n:
                    r.text = pat.sub(replacement.replace("\\", "\\\\"), r.text)
                    count += n
                runs.append(r)
                e = emb.get(s.get("font", ""))
                if e and e[1] in ("ttf", "otf"):
                    emb_map[r.family + ("|b" if r.bold else "") + ("|i" if r.italic else "")] = e[0]
            # occorrenze a cavallo di due span: si unisce la riga
            joined = "".join(s["text"] for s in l["spans"])
            if not any(pat.search(s["text"]) for s in l["spans"]) and pat.search(joined):
                base = runs[0]
                base.text = pat.sub(replacement.replace("\\", "\\\\"), joined)
                runs = [base]
                count += len(pat.findall(joined))
            lr = pymupdf.Rect(l["bbox"])
            h = lr.height
            apply_internal_redactions(page, [pymupdf.Rect(lr.x0 + 0.3, lr.y0 + h * 0.3, lr.x1 - 0.3, lr.y1 - h * 0.3)])
            para = Para(runs=runs, line_height=1.0)
            rot = dir_to_rotate(l.get("dir", (1, 0)))
            mb = page.mediabox
            # il riquadro parte dalla riga originale e si allunga nella direzione del testo
            box = pymupdf.Rect(lr)
            if rot == 0:
                box.x1 = max(mb.x1, lr.x1 + lr.width)
            elif rot == 180:
                box.x0 = min(mb.x0, lr.x0 - lr.width)
            elif rot == 90:
                box.y0 = min(mb.y0, lr.y0 - lr.height)
            else:
                box.y1 = max(mb.y1, lr.y1 + lr.height)
            _, w = insert_paras(page, box, [para], emb_map, grow=False, rotate=rot)
            warnings.extend(w)
    return count, sorted(set(warnings))
