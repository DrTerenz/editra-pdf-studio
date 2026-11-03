"""Filigrana, sfondo, intestazioni e piè di pagina, numeri di pagina, numerazione Bates."""
from __future__ import annotations

import datetime as _dt
import os

import pymupdf

from .common import hex_to_rgb
from ..i18n import T

POSITIONS = ["alto-sinistra", "alto-centro", "alto-destra", "basso-sinistra", "basso-centro", "basso-destra"]

BASE_FONTS = {"Helvetica": "helv", "Helvetica grassetto": "hebo", "Times": "tiro", "Times grassetto": "tibo",
              "Courier": "cour", "Courier grassetto": "cobo"}


def _font_args(font: str) -> dict:
    """Font base14 o file di Windows."""
    if font in BASE_FONTS:
        return {"fontname": BASE_FONTS[font]}
    from .. import fonts
    path = fonts.font_file(font)
    if path and not path.lower().endswith(".ttc"):
        return {"fontname": "F" + str(abs(hash(path)) % 10000), "fontfile": path}
    return {"fontname": "helv"}


def _text_width(text: str, size: float, font: str) -> float:
    fa = _font_args(font)
    try:
        f = pymupdf.Font(fontfile=fa["fontfile"]) if "fontfile" in fa else pymupdf.Font(fa["fontname"])
        return f.text_length(text, fontsize=size)
    except Exception:
        return pymupdf.get_text_length(text, fontsize=size)


def expand_tokens(template: str, n: int, total: int, filename: str, bates: str = "") -> str:
    now = _dt.datetime.now()
    return (template.replace("{n}", str(n)).replace("{N}", str(total))
            .replace("{data}", now.strftime("%d/%m/%Y")).replace("{ora}", now.strftime("%H:%M"))
            .replace("{file}", filename).replace("{bates}", bates))


def _display_to_pdf(page: pymupdf.Page, p: pymupdf.Point) -> pymupdf.Point:
    return p * page.derotation_matrix


def place_text(page: pymupdf.Page, text: str, position: str, font: str, size: float, color: str,
               margin_x: float = 36, margin_y: float = 28, opacity: float = 1.0) -> None:
    """Scrive una riga di testo in una delle 6 posizioni, rispetto alla pagina come appare."""
    W, H = page.rect.width, page.rect.height
    tw = _text_width(text, size, font)
    vert, horiz = position.split("-")
    x = {"sinistra": margin_x, "centro": (W - tw) / 2, "destra": W - margin_x - tw}[horiz]
    y = margin_y + size if vert == "alto" else H - margin_y
    pt = _display_to_pdf(page, pymupdf.Point(x, y))
    page.insert_text(pt, text, fontsize=size, color=hex_to_rgb(color), rotate=page.rotation,
                     fill_opacity=opacity, **_font_args(font))


def header_footer(doc: pymupdf.Document, pages: list[int], items: dict[str, str], font: str, size: float,
                  color: str, margin_x: float, margin_y: float, start_number: int = 1,
                  filename: str = "") -> None:
    """items: {posizione: modello}; modelli con {n} {N} {data} {ora} {file}."""
    total = doc.page_count
    for k, pno in enumerate(pages):
        page = doc[pno]
        for pos, tpl in items.items():
            if not tpl.strip():
                continue
            text = expand_tokens(tpl, start_number + k if start_number else pno + 1, total, filename)
            place_text(page, text, pos, font, size, color, margin_x, margin_y)


def bates(doc: pymupdf.Document, pages: list[int], prefix: str, suffix: str, start: int, digits: int,
          position: str, font: str, size: float, color: str, margin_x: float = 36, margin_y: float = 28) -> str:
    """Numerazione Bates; ritorna l'intervallo applicato (primo-ultimo)."""
    first = last = ""
    for k, pno in enumerate(pages):
        code = f"{prefix}{start + k:0{digits}d}{suffix}"
        place_text(doc[pno], code, position, font, size, color, margin_x, margin_y)
        first = first or code
        last = code
    return f"{first} – {last}"


def _watermark_page(text: str, font: str, size: float, color: str, opacity: float) -> pymupdf.Document:
    """Pagina con solo il testo della filigrana, da sovrapporre con show_pdf_page."""
    lines = text.split("\n")
    widths = [_text_width(l, size, font) for l in lines]
    w = max(widths) + 10
    h = size * 1.25 * len(lines) + 10
    d = pymupdf.open()
    p = d.new_page(width=w, height=h)
    for i, (line, lw) in enumerate(zip(lines, widths)):
        p.insert_text(((w - lw) / 2, 5 + size * (i + 1) * 1.15), line, fontsize=size, color=hex_to_rgb(color),
                      fill_opacity=opacity, **_font_args(font))
    return d


def watermark_text(doc: pymupdf.Document, pages: list[int], text: str, font: str = T('Helvetica grassetto'),
                   size: float = 60, color: str = "#c62828", opacity: float = 0.25, rotation: float = 45,
                   overlay: bool = True, position: str = "centro", scale_to_page: float = 0) -> None:
    wm = _watermark_page(text, font, size, color, opacity)
    _apply_overlay(doc, pages, wm, rotation, overlay, position, scale_to_page)
    wm.close()


def watermark_image(doc: pymupdf.Document, pages: list[int], path: str, opacity: float = 0.3,
                    rotation: float = 0, overlay: bool = True, position: str = "centro",
                    scale_to_page: float = 0.5) -> None:
    from PIL import Image
    import io
    img = Image.open(path).convert(T('RGBA'))
    if opacity < 1:
        alpha = img.getchannel("A").point(lambda a: int(a * opacity))
        img.putalpha(alpha)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    d = pymupdf.open()
    p = d.new_page(width=img.width * 0.75, height=img.height * 0.75)
    p.insert_image(p.rect, stream=buf.getvalue())
    _apply_overlay(doc, pages, d, rotation, overlay, position, scale_to_page or 0.5)
    d.close()


def _apply_overlay(doc, pages, src: pymupdf.Document, rotation: float, overlay: bool, position: str,
                   scale_to_page: float) -> None:
    sw, sh = src[0].rect.width, src[0].rect.height
    import math
    a = math.radians(rotation)
    # ingombro del contenuto ruotato
    bw = abs(sw * math.cos(a)) + abs(sh * math.sin(a))
    bh = abs(sw * math.sin(a)) + abs(sh * math.cos(a))
    for pno in pages:
        page = doc[pno]
        W, H = page.rect.width, page.rect.height
        k = 1.0
        if scale_to_page:
            k = min(W * scale_to_page / bw, H * scale_to_page / bh)
        else:
            k = min(1.0, W * 0.95 / bw, H * 0.95 / bh)
        w, h = bw * k, bh * k
        if position == "alto":
            cx, cy = W / 2, h / 2 + 20
        elif position == "basso":
            cx, cy = W / 2, H - h / 2 - 20
        else:
            cx, cy = W / 2, H / 2
        rect_disp = pymupdf.Rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        rect = rect_disp * page.derotation_matrix
        page.show_pdf_page(rect, src, 0, overlay=overlay, rotate=rotation + page.rotation, keep_proportion=True)


def background(doc: pymupdf.Document, pages: list[int], color: str | None = None, image: str | None = None,
               opacity: float = 1.0) -> None:
    for pno in pages:
        page = doc[pno]
        if image:
            page.insert_image(page.mediabox, filename=image, overlay=False, keep_proportion=False)
        elif color:
            shape = page.new_shape()
            shape.draw_rect(page.mediabox)
            shape.finish(fill=hex_to_rgb(color), color=None, fill_opacity=opacity)
            shape.commit(overlay=False)


def page_numbers(doc: pymupdf.Document, pages: list[int], template: str = T('Pagina {n} di {N}'),
                 position: str = "basso-centro", font: str = T('Helvetica'), size: float = 10,
                 color: str = "#000000", start: int = 1, margin_x: float = 36, margin_y: float = 24) -> None:
    total = doc.page_count
    for k, pno in enumerate(pages):
        text = template.replace("{n}", str(start + k)).replace("{N}", str(total))
        place_text(doc[pno], text, position, font, size, color, margin_x, margin_y)


def add_link(page: pymupdf.Page, rect: pymupdf.Rect, *, page_target: int | None = None, uri: str | None = None,
             file: str | None = None) -> None:
    if uri:
        link = {"kind": pymupdf.LINK_URI, "from": rect, "uri": uri}
    elif file:
        link = {"kind": pymupdf.LINK_LAUNCH, "from": rect, "file": file}
    else:
        link = {"kind": pymupdf.LINK_GOTO, "from": rect, "page": page_target or 0, "to": pymupdf.Point(0, 0)}
    page.insert_link(link)


def detect_urls(doc: pymupdf.Document) -> int:
    """Crea collegamenti cliccabili sugli indirizzi web scritti nel testo."""
    import re
    pat = re.compile(r"(https?://[^\s<>\"]+|www\.[^\s<>\"]+)", re.I)
    n = 0
    for page in doc:
        existing = [pymupdf.Rect(l["from"]) for l in page.get_links()]
        for w in page.get_text("words"):
            m = pat.fullmatch(w[4].rstrip(".,;)"))
            if not m:
                continue
            r = pymupdf.Rect(w[:4])
            if any(r.intersects(e) for e in existing):
                continue
            uri = m.group(0)
            if not uri.lower().startswith("http"):
                uri = "https://" + uri
            page.insert_link({"kind": pymupdf.LINK_URI, "from": r, "uri": uri})
            n += 1
    return n


def file_basename(path: str | None) -> str:
    return os.path.basename(path) if path else ""
