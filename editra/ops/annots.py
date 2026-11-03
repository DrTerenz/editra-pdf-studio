"""Annotazioni: creazione, spostamento, proprietà, elenco, esportazione."""
from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass

import pymupdf

from .common import hex_to_rgb, rgb_to_hex
from ..i18n import T

TYPE_NAMES = {
    pymupdf.PDF_ANNOT_TEXT: T('Nota'), pymupdf.PDF_ANNOT_FREE_TEXT: T('Casella di testo'),
    pymupdf.PDF_ANNOT_LINE: T('Linea'), pymupdf.PDF_ANNOT_SQUARE: T('Rettangolo'),
    pymupdf.PDF_ANNOT_CIRCLE: T('Ellisse'), pymupdf.PDF_ANNOT_POLYGON: T('Poligono'),
    pymupdf.PDF_ANNOT_POLY_LINE: T('Spezzata'), pymupdf.PDF_ANNOT_HIGHLIGHT: T('Evidenziazione'),
    pymupdf.PDF_ANNOT_UNDERLINE: T('Sottolineatura'), pymupdf.PDF_ANNOT_SQUIGGLY: T('Ondulata'),
    pymupdf.PDF_ANNOT_STRIKE_OUT: T('Barrato'), pymupdf.PDF_ANNOT_STAMP: T('Timbro'),
    pymupdf.PDF_ANNOT_CARET: T('Inserimento'), pymupdf.PDF_ANNOT_INK: T('Disegno a mano'),
    pymupdf.PDF_ANNOT_FILE_ATTACHMENT: T('Allegato'), pymupdf.PDF_ANNOT_REDACT: T('Redazione'),
    pymupdf.PDF_ANNOT_LINK: T('Collegamento'),
}

STAMPS = [
    (T('Approvato'), pymupdf.STAMP_Approved), (T('Non approvato'), pymupdf.STAMP_NotApproved),
    (T('Bozza'), pymupdf.STAMP_Draft), (T('Finale'), pymupdf.STAMP_Final),
    (T('Riservato'), pymupdf.STAMP_Confidential), (T('Per commenti'), pymupdf.STAMP_ForComment),
    (T("Così com'è"), pymupdf.STAMP_AsIs), (T('Scaduto'), pymupdf.STAMP_Expired),
    (T('Sperimentale'), pymupdf.STAMP_Experimental), (T('Dipartimentale'), pymupdf.STAMP_Departmental),
    (T('Pubblico'), pymupdf.STAMP_ForPublicRelease), (T('Non pubblico'), pymupdf.STAMP_NotForPublicRelease),
    (T('Venduto'), pymupdf.STAMP_Sold), (T('Top secret'), pymupdf.STAMP_TopSecret),
]

NOTE_ICONS = [(T('Commento'), T('Comment')), (T('Nota'), T('Note')), (T('Chiave'), T('Key')), (T('Aiuto'), T('Help')),
              (T('Paragrafo'), T('Paragraph')), (T('Nuovo paragrafo'), T('NewParagraph')), (T('Inserisci'), T('Insert'))]

# tipi i cui punti vanno ricreati per spostarli
_VERTEX_TYPES = (pymupdf.PDF_ANNOT_LINE, pymupdf.PDF_ANNOT_POLYGON, pymupdf.PDF_ANNOT_POLY_LINE, pymupdf.PDF_ANNOT_INK)
_MARKUP_TYPES = (pymupdf.PDF_ANNOT_HIGHLIGHT, pymupdf.PDF_ANNOT_UNDERLINE, pymupdf.PDF_ANNOT_SQUIGGLY,
                 pymupdf.PDF_ANNOT_STRIKE_OUT)


@dataclass
class Style:
    color: str | None = "#e53935"
    fill: str | None = None
    width: float = 1.5
    opacity: float = 1.0
    author: str = ""
    fontsize: float = 12
    font: str = "helv"
    text_color: str = "#000000"
    dashed: bool = False


def _finish(annot: pymupdf.Annot, st: Style, content: str | None = None, set_colors: bool = True) -> pymupdf.Annot:
    if set_colors:
        colors = {}
        if st.color is not None:
            colors["stroke"] = hex_to_rgb(st.color)
        if st.fill is not None:
            colors["fill"] = hex_to_rgb(st.fill)
        if colors:
            try:
                annot.set_colors(**colors)
            except Exception:
                pass
    try:
        annot.set_border(width=st.width, dashes=[3, 3] if st.dashed else None)
    except Exception:
        pass
    annot.set_opacity(st.opacity)
    info = {"title": st.author or "", "modDate": pymupdf.get_pdf_now()}
    if content is not None:
        info["content"] = content
    annot.set_info(info)
    annot.update()
    return annot


def add_markup(page: pymupdf.Page, kind: str, quads, st: Style) -> pymupdf.Annot:
    fn = {"highlight": page.add_highlight_annot, "underline": page.add_underline_annot,
          "strike": page.add_strikeout_annot, "squiggly": page.add_squiggly_annot}[kind]
    a = fn(quads)
    a.set_colors(stroke=hex_to_rgb(st.color or "#ffeb3b"))
    a.set_opacity(st.opacity)
    a.set_info(title=st.author or "")
    a.update()
    return a


def add_note(page: pymupdf.Page, point: pymupdf.Point, text: str, icon: str, st: Style) -> pymupdf.Annot:
    a = page.add_text_annot(point, text, icon=icon)
    a.set_colors(stroke=hex_to_rgb(st.color or "#ffd54f"))
    a.set_info(title=st.author or "", content=text)
    a.update()
    return a


def add_freetext(page: pymupdf.Page, rect: pymupdf.Rect, text: str, st: Style, callout=None) -> pymupdf.Annot:
    kw = {}
    if callout:
        kw["callout"] = callout
        kw["line_end"] = pymupdf.PDF_ANNOT_LE_OPEN_ARROW
    a = page.add_freetext_annot(
        rect, text, fontsize=st.fontsize, fontname=st.font, text_color=hex_to_rgb(st.text_color),
        fill_color=hex_to_rgb(st.fill) if st.fill else None,
        border_width=st.width if st.color else 0, opacity=st.opacity, rotate=page.rotation, **kw)
    a.set_info(title=st.author or "", content=text)
    a.update()
    return a


def add_shape(page: pymupdf.Page, kind: str, pts: list[pymupdf.Point], st: Style) -> pymupdf.Annot:
    """kind: line, arrow, rect, ellipse, polygon, polyline, cloud."""
    if kind in ("line", "arrow"):
        a = page.add_line_annot(pts[0], pts[1])
        if kind == "arrow":
            a.set_line_ends(pymupdf.PDF_ANNOT_LE_NONE, pymupdf.PDF_ANNOT_LE_CLOSED_ARROW)
    elif kind == "rect":
        a = page.add_rect_annot(pymupdf.Rect(pts[0], pts[1]).normalize())
    elif kind == "ellipse":
        a = page.add_circle_annot(pymupdf.Rect(pts[0], pts[1]).normalize())
    elif kind == "polygon":
        a = page.add_polygon_annot(pts)
    elif kind == "polyline":
        a = page.add_polyline_annot(pts)
    else:
        raise ValueError(kind)
    return _finish(a, st)


def add_ink(page: pymupdf.Page, strokes: list[list[pymupdf.Point]], st: Style) -> pymupdf.Annot:
    a = page.add_ink_annot([[(p.x, p.y) for p in s] for s in strokes])
    return _finish(a, Style(st.color, None, st.width, st.opacity, st.author))


def add_stamp(page: pymupdf.Page, rect: pymupdf.Rect, stamp: int, st: Style) -> pymupdf.Annot:
    a = page.add_stamp_annot(rect, stamp=stamp)
    a.set_opacity(st.opacity)
    a.set_info(title=st.author or "")
    a.update()
    return a


def add_text_stamp(page: pymupdf.Page, rect: pymupdf.Rect, text: str, color: str, st: Style,
                   with_date: bool = True) -> None:
    """Timbro personalizzato (testo con bordo arrotondato), scritto nel contenuto della pagina."""
    rgb = hex_to_rgb(color)
    sub = (st.author + " " if st.author else "") + (_dt.datetime.now().strftime("%d/%m/%Y %H:%M") if with_date else "")
    shape = page.new_shape()
    shape.draw_rect(rect, radius=0.15)
    shape.finish(color=rgb, width=2.5, stroke_opacity=st.opacity, fill_opacity=0)
    shape.commit()
    h = rect.height
    main_h = h * (0.62 if sub.strip() else 1)
    word = text.upper()
    # corpo che fa stare la scritta sia in larghezza sia in altezza
    unit = pymupdf.get_text_length(word, fontname="hebo", fontsize=1) or 1
    fs = max(4.0, min(main_h * 0.55, rect.width * 0.86 / unit))
    tw = unit * fs
    page.insert_text(pymupdf.Point((rect.x0 + rect.x1 - tw) / 2, rect.y0 + main_h * 0.5 + fs * 0.36), word,
                     fontsize=fs, fontname="hebo", color=rgb, fill_opacity=st.opacity)
    if sub.strip():
        ss = min(h * 0.16, 9.0)
        sw = pymupdf.get_text_length(sub.strip(), fontname="helv", fontsize=ss)
        page.insert_text(pymupdf.Point((rect.x0 + rect.x1 - sw) / 2, rect.y1 - h * 0.14), sub.strip(),
                         fontsize=ss, fontname="helv", color=rgb, fill_opacity=st.opacity)


def add_file_attachment(page: pymupdf.Page, point: pymupdf.Point, path: str, st: Style) -> pymupdf.Annot:
    import os
    with open(path, "rb") as f:
        data = f.read()
    a = page.add_file_annot(point, data, os.path.basename(path), desc=os.path.basename(path))
    a.set_info(title=st.author or "")
    a.update()
    return a


def add_measure(page: pymupdf.Page, p1: pymupdf.Point, p2: pymupdf.Point, scale: float, unit: str,
                st: Style) -> tuple[pymupdf.Annot, str]:
    """Linea di quota con il valore misurato. scale = unità reali per millimetro sulla carta."""
    dist_pt = math.hypot(p2.x - p1.x, p2.y - p1.y)
    mm = dist_pt * 25.4 / 72
    value = mm * scale
    label = _format_measure(value, unit)
    a = page.add_line_annot(p1, p2)
    a.set_line_ends(pymupdf.PDF_ANNOT_LE_OPEN_ARROW, pymupdf.PDF_ANNOT_LE_OPEN_ARROW)
    _finish(a, st, content=T('Distanza: {}').format(label))
    mid = pymupdf.Point((p1.x + p2.x) / 2, (p1.y + p2.y) / 2)
    r = pymupdf.Rect(mid.x - 40, mid.y - 16, mid.x + 40, mid.y - 2)
    t = page.add_freetext_annot(r, label, fontsize=9, text_color=hex_to_rgb(st.color or "#000"),
                                fill_color=(1, 1, 1), align=1, rotate=page.rotation)
    t.set_info(title=st.author or "", content=T('Distanza: {}').format(label))
    t.update()
    return a, label


def measure_area(points: list[pymupdf.Point], scale: float, unit: str) -> str:
    pts_mm = [(p.x * 25.4 / 72 * scale, p.y * 25.4 / 72 * scale) for p in points]
    area = 0.0
    for (x1, y1), (x2, y2) in zip(pts_mm, pts_mm[1:] + pts_mm[:1]):
        area += x1 * y2 - x2 * y1
    area = abs(area) / 2
    per = sum(math.hypot(x2 - x1, y2 - y1) for (x1, y1), (x2, y2) in zip(pts_mm, pts_mm[1:] + pts_mm[:1]))
    return T('Area: {} · Perimetro: {}').format(_format_measure(area, unit, 2), _format_measure(per, unit))


def _format_measure(value_mm_units: float, unit: str, power: int = 1) -> str:
    factor = {"mm": 1, "cm": 10, "m": 1000, "in": 25.4, "pt": 25.4 / 72}.get(unit, 1) ** power
    v = value_mm_units / factor
    suffix = unit + ("²" if power == 2 else "")
    from ..i18n import LANG
    if LANG == "en":
        return f"{v:,.2f} {suffix}"
    return f"{v:,.2f} {suffix}".replace(",", "X").replace(".", ",").replace("X", ".")


def add_area_measure(page: pymupdf.Page, pts: list[pymupdf.Point], scale: float, unit: str, st: Style):
    a = page.add_polygon_annot(pts)
    label = measure_area(pts, scale, unit)
    _finish(a, Style(st.color, st.fill or None, st.width, min(st.opacity, 0.8), st.author), content=label)
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    t = page.add_freetext_annot(pymupdf.Rect(cx - 90, cy - 8, cx + 90, cy + 8), label, fontsize=8,
                                text_color=hex_to_rgb(st.color or "#000"), fill_color=(1, 1, 1), align=1,
                                rotate=page.rotation)
    t.set_info(title=st.author or "", content=label)
    t.update()
    return a, label


# ------------------------------------------------------------ modifica
def annot_by_xref(page: pymupdf.Page, xref: int) -> pymupdf.Annot | None:
    for a in page.annots():
        if a.xref == xref:
            return a
    return None


def annot_at(page: pymupdf.Page, point: pymupdf.Point, tol: float = 3) -> pymupdf.Annot | None:
    """Annotazione sotto il punto (coordinate PDF); preferisce la più piccola."""
    best = None
    for a in page.annots():
        if a.type[0] in (pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_LINK, pymupdf.PDF_ANNOT_WIDGET):
            continue
        r = a.rect + (-tol, -tol, tol, tol)
        if point in r:
            if best is None or a.rect.get_area() < best.rect.get_area():
                best = a
    return best


def can_move(annot: pymupdf.Annot) -> bool:
    return annot.type[0] not in _MARKUP_TYPES


def move_annot(page: pymupdf.Page, annot: pymupdf.Annot, dx: float, dy: float) -> int:
    """Sposta un'annotazione; ritorna lo xref (può cambiare se va ricreata)."""
    t = annot.type[0]
    if t in _VERTEX_TYPES:
        return _recreate_shifted(page, annot, dx, dy)
    r = annot.rect
    annot.set_rect(pymupdf.Rect(r.x0 + dx, r.y0 + dy, r.x1 + dx, r.y1 + dy))
    annot.update()
    return annot.xref


def resize_annot(page: pymupdf.Page, annot: pymupdf.Annot, new_rect: pymupdf.Rect) -> int:
    t = annot.type[0]
    if t in _VERTEX_TYPES or t in _MARKUP_TYPES or t == pymupdf.PDF_ANNOT_TEXT:
        return annot.xref
    annot.set_rect(pymupdf.Rect(new_rect).normalize())
    annot.update()
    return annot.xref


def _recreate_shifted(page: pymupdf.Page, annot: pymupdf.Annot, dx: float, dy: float) -> int:
    t = annot.type[0]
    verts = annot.vertices or []
    colors = annot.colors
    border = annot.border
    opacity = annot.opacity
    info = annot.info
    line_ends = annot.line_ends
    if t == pymupdf.PDF_ANNOT_INK:
        strokes = [[(x + dx, y + dy) for x, y in s] for s in verts]
        page.delete_annot(annot)
        new = page.add_ink_annot(strokes)
    else:
        pts = [pymupdf.Point(x + dx, y + dy) for x, y in verts]
        page.delete_annot(annot)
        if t == pymupdf.PDF_ANNOT_LINE:
            new = page.add_line_annot(pts[0], pts[1])
            if line_ends:
                new.set_line_ends(*line_ends)
        elif t == pymupdf.PDF_ANNOT_POLYGON:
            new = page.add_polygon_annot(pts)
        else:
            new = page.add_polyline_annot(pts)
    try:
        new.set_colors(stroke=colors.get("stroke"), fill=colors.get("fill") or None)
    except Exception:
        pass
    if border and border.get("width") is not None:
        new.set_border(width=border.get("width"), dashes=border.get("dashes") or None)
    if opacity is not None and opacity >= 0:
        new.set_opacity(opacity)
    new.set_info(info)
    new.update()
    return new.xref


def annot_props(annot: pymupdf.Annot) -> dict:
    c = annot.colors or {}
    b = annot.border or {}
    return {
        "type": annot.type[0], "type_name": TYPE_NAMES.get(annot.type[0], annot.type[1]),
        "color": rgb_to_hex(c.get("stroke")), "fill": rgb_to_hex(c.get("fill")),
        "width": b.get("width", 1) if b.get("width", -1) >= 0 else 1,
        "opacity": annot.opacity if annot.opacity is not None and annot.opacity >= 0 else 1.0,
        "content": annot.info.get("content", ""), "author": annot.info.get("title", ""),
        "subject": annot.info.get("subject", ""),
        "modified": annot.info.get("modDate", ""), "locked": bool(annot.flags & pymupdf.PDF_ANNOT_IS_LOCKED),
    }


def set_annot_props(annot: pymupdf.Annot, props: dict) -> None:
    t = annot.type[0]
    if "color" in props or "fill" in props:
        kw = {}
        if props.get("color"):
            kw["stroke"] = hex_to_rgb(props["color"])
        if t in (pymupdf.PDF_ANNOT_SQUARE, pymupdf.PDF_ANNOT_CIRCLE, pymupdf.PDF_ANNOT_POLYGON,
                 pymupdf.PDF_ANNOT_LINE, pymupdf.PDF_ANNOT_POLY_LINE, pymupdf.PDF_ANNOT_FREE_TEXT):
            kw["fill"] = hex_to_rgb(props["fill"]) if props.get("fill") else []
        if t == pymupdf.PDF_ANNOT_FREE_TEXT:
            # nelle caselle di testo il colore del bordo e del testo stanno nell'aspetto
            pass
        else:
            try:
                annot.set_colors(**kw)
            except Exception:
                pass
    if "width" in props and t not in _MARKUP_TYPES + (pymupdf.PDF_ANNOT_TEXT, pymupdf.PDF_ANNOT_STAMP):
        try:
            annot.set_border(width=float(props["width"]))
        except Exception:
            pass
    if "opacity" in props:
        annot.set_opacity(float(props["opacity"]))
    info = {}
    for k in ("content", "author", "subject"):
        if k in props:
            info["title" if k == "author" else k] = props[k]
    if info:
        info["modDate"] = pymupdf.get_pdf_now()
        annot.set_info(info)
    if "locked" in props:
        fl = annot.flags
        fl = fl | pymupdf.PDF_ANNOT_IS_LOCKED if props["locked"] else fl & ~pymupdf.PDF_ANNOT_IS_LOCKED
        annot.set_flags(fl)
    if t == pymupdf.PDF_ANNOT_FREE_TEXT and ("color" in props or "fill" in props):
        annot.update(text_color=hex_to_rgb(props.get("text_color") or props.get("color")) if (props.get("text_color") or props.get("color")) else None,
                     fill_color=hex_to_rgb(props["fill"]) if props.get("fill") else None)
    else:
        annot.update()


def list_annots(doc: pymupdf.Document) -> list[dict]:
    out = []
    for pno, page in enumerate(doc):
        for a in page.annots():
            if a.type[0] in (pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_LINK, pymupdf.PDF_ANNOT_WIDGET):
                continue
            d = annot_props(a)
            d.update(page=pno, xref=a.xref, rect=tuple(a.rect))
            if a.type[0] in _MARKUP_TYPES:
                try:
                    d["marked_text"] = page.get_textbox(a.rect).strip()
                except Exception:
                    d["marked_text"] = ""
            out.append(d)
    return out


def comments_summary_html(doc: pymupdf.Document, title: str) -> str:
    import html
    rows = []
    for d in list_annots(doc):
        if d["type"] == pymupdf.PDF_ANNOT_REDACT:
            continue
        text = d.get("content") or d.get("marked_text") or ""
        rows.append(T('<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>').format(d['page'] + 1, html.escape(d['type_name']), html.escape(d['author']), html.escape(_pdf_date(d['modified'])), html.escape(text)))
    return (f"<html><head><meta charset='utf-8'><title>{T('Commenti')} - {html.escape(title)}</title>"
            "<style>body{font-family:Segoe UI,Arial;margin:30px}table{border-collapse:collapse;width:100%}"
            "td,th{border:1px solid #ccc;padding:6px;text-align:left;vertical-align:top}th{background:#f0ecf8}</style>"
            f"</head><body><h1>{T('Riepilogo commenti')}</h1><p>{html.escape(title)}</p>"
            f"<table><tr><th>{T('Pagina')}</th><th>{T('Tipo')}</th><th>{T('Autore')}</th><th>{T('Data')}</th>"
            f"<th>{T('Testo')}</th></tr>"
            + "".join(rows) + "</table></body></html>")


def _pdf_date(s: str) -> str:
    if s and s.startswith("D:") and len(s) >= 16:
        return f"{s[8:10]}/{s[6:8]}/{s[2:6]} {s[10:12]}:{s[12:14]}"
    return s or ""


def delete_all_annots(doc: pymupdf.Document, pages=None, keep_redactions: bool = True) -> int:
    n = 0
    for pno in (pages if pages is not None else range(doc.page_count)):
        page = doc[pno]
        for a in list(page.annots()):
            if keep_redactions and a.type[0] == pymupdf.PDF_ANNOT_REDACT:
                continue
            page.delete_annot(a)
            n += 1
    return n


def flatten(doc: pymupdf.Document, annots: bool = True, widgets: bool = True) -> None:
    """Rende annotazioni e/o campi parte fissa della pagina."""
    doc.bake(annots=annots, widgets=widgets)
