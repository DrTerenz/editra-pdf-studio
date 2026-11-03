"""Moduli compilabili: creazione campi, compilazione, esportazione e importazione dati."""
from __future__ import annotations

import json

import pymupdf

from .common import hex_to_rgb
from ..i18n import T

FIELD_TYPES = {
    "text": (pymupdf.PDF_WIDGET_TYPE_TEXT, T('Campo di testo')),
    "checkbox": (pymupdf.PDF_WIDGET_TYPE_CHECKBOX, T('Casella di controllo')),
    "radio": (pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON, T('Pulsante di scelta')),
    "combobox": (pymupdf.PDF_WIDGET_TYPE_COMBOBOX, T('Elenco a discesa')),
    "listbox": (pymupdf.PDF_WIDGET_TYPE_LISTBOX, T('Casella di riepilogo')),
    "signature": (pymupdf.PDF_WIDGET_TYPE_SIGNATURE, T('Campo firma')),
    "button": (pymupdf.PDF_WIDGET_TYPE_BUTTON, T('Pulsante')),
}


def unique_name(doc: pymupdf.Document, base: str) -> str:
    names = {w.field_name for p in doc for w in p.widgets()}
    if base not in names:
        return base
    i = 2
    while f"{base}_{i}" in names:
        i += 1
    return f"{base}_{i}"


def create_field(page: pymupdf.Page, kind: str, rect: pymupdf.Rect, name: str, *, value: str = "",
                 choices: list[str] | None = None, tooltip: str = "", required: bool = False,
                 multiline: bool = False, fontsize: float = 0, border_color: str = "#7a6aa8",
                 fill_color: str | None = None, max_len: int = 0, export_value: str = "Si") -> pymupdf.Widget:
    w = pymupdf.Widget()
    w.field_type = FIELD_TYPES[kind][0]
    w.field_name = name
    w.rect = pymupdf.Rect(rect).normalize()
    w.field_label = tooltip or name
    w.border_color = hex_to_rgb(border_color) if border_color else None
    w.fill_color = hex_to_rgb(fill_color) if fill_color else None
    w.border_width = 1
    w.text_fontsize = fontsize
    flags = 0
    if required:
        flags |= pymupdf.PDF_FIELD_IS_REQUIRED
    if kind == "text":
        if multiline:
            flags |= pymupdf.PDF_TX_FIELD_IS_MULTILINE
        if max_len:
            w.text_maxlen = max_len
        w.field_value = value
    elif kind in ("combobox", "listbox"):
        w.choice_values = choices or [T('Opzione 1'), T('Opzione 2')]
        w.field_value = value or (w.choice_values[0] if kind == "combobox" else "")
        if kind == "combobox":
            flags |= pymupdf.PDF_CH_FIELD_IS_EDIT if False else 0
    elif kind == "checkbox":
        w.field_value = False
    elif kind == "radio":
        w.field_value = False
    elif kind == "button":
        w.button_caption = value or name
        flags |= pymupdf.PDF_BTN_FIELD_IS_PUSHBUTTON
    w.field_flags = flags
    page.add_widget(w)
    return w


def widget_at(page: pymupdf.Page, point: pymupdf.Point) -> pymupdf.Widget | None:
    for w in page.widgets():
        if point in w.rect:
            return w
    return None


def widget_by_xref(page: pymupdf.Page, xref: int) -> pymupdf.Widget | None:
    for w in page.widgets():
        if w.xref == xref:
            return w
    return None


def set_value(page: pymupdf.Page, xref: int, value) -> None:
    w = widget_by_xref(page, xref)
    if w is None:
        return
    if w.field_type == pymupdf.PDF_WIDGET_TYPE_CHECKBOX:
        w.field_value = w.on_state() if value else T('Off')
    elif w.field_type == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
        w.field_value = w.on_state() if value else T('Off')
    else:
        _set_text(w, value)
        return
    w.update()


def _set_text(w: pymupdf.Widget, value) -> None:
    """Imposta un testo; il valore vuoto va scritto a mano perché PyMuPDF lo ignora."""
    value = "" if value is None else str(value)
    if value == "":
        w.field_value = " "
        w.update()
        doc = w.parent.parent
        # il valore sta nel campo: nel widget stesso se ha il nome (/T), altrimenti nel genitore
        target = w.xref
        if doc.xref_get_key(w.xref, "T")[0] == "null":
            kind, val = doc.xref_get_key(w.xref, "Parent")
            if kind == "xref":
                target = int(val.split()[0])
        doc.xref_set_key(target, "V", "()")
    else:
        w.field_value = value
        w.update()


def toggle(page: pymupdf.Page, xref: int) -> None:
    w = widget_by_xref(page, xref)
    if w is None:
        return
    on = w.on_state()
    checked = w.field_value not in (T('Off'), False, "", None)
    if w.field_type == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
        w.field_value = on
    else:
        w.field_value = T('Off') if checked else on
    w.update()


def delete_field(page: pymupdf.Page, xref: int) -> None:
    w = widget_by_xref(page, xref)
    if w is not None:
        page.delete_widget(w)


def all_fields(doc: pymupdf.Document) -> list[dict]:
    out = []
    for pno, page in enumerate(doc):
        for w in page.widgets():
            out.append({"page": pno, "xref": w.xref, "name": w.field_name, "type": w.field_type_string,
                        "value": w.field_value, "rect": tuple(w.rect)})
    return out


def export_data(doc: pymupdf.Document, path: str) -> int:
    data = {}
    for f in all_fields(doc):
        if f["type"] in (T('Signature'), T('Button')):
            continue
        v = f["value"]
        data[f["name"]] = v if isinstance(v, (str, int, float, bool)) or v is None else str(v)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return len(data)


def import_data(doc: pymupdf.Document, path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    n = 0
    for page in doc:
        for w in page.widgets():
            if w.field_name in data:
                v = data[w.field_name]
                if w.field_type in (pymupdf.PDF_WIDGET_TYPE_CHECKBOX, pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON):
                    w.field_value = v if isinstance(v, str) else (w.on_state() if v else T('Off'))
                    w.update()
                else:
                    _set_text(w, v)
                n += 1
    return n


def reset_form(doc: pymupdf.Document) -> None:
    for page in doc:
        for w in page.widgets():
            if w.field_type in (pymupdf.PDF_WIDGET_TYPE_CHECKBOX, pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON):
                w.field_value = T('Off')
                w.update()
            elif w.field_type in (pymupdf.PDF_WIDGET_TYPE_SIGNATURE, pymupdf.PDF_WIDGET_TYPE_BUTTON):
                continue
            else:
                _set_text(w, "")


def auto_detect_fields(doc: pymupdf.Document, pages=None) -> int:
    """Crea campi di testo sopra le righe orizzontali e i trattini bassi (moduli 'cartacei')."""
    n = 0
    for pno in (pages if pages is not None else range(doc.page_count)):
        page = doc[pno]
        existing = [w.rect for w in page.widgets()]
        cands = []
        for d in page.get_drawings():
            for item in d.get("items", []):
                if item[0] == "l":
                    p1, p2 = item[1], item[2]
                    if abs(p1.y - p2.y) < 0.8 and abs(p2.x - p1.x) > 40:
                        x0, x1 = sorted((p1.x, p2.x))
                        cands.append(pymupdf.Rect(x0, p1.y - 14, x1, p1.y - 0.5))
                elif item[0] == "re":
                    r = item[1]
                    if r.height < 1.5 and r.width > 40:
                        cands.append(pymupdf.Rect(r.x0, r.y0 - 14, r.x1, r.y0 - 0.5))
        for w in page.get_text("words"):
            if set(w[4]) <= set("_.") and len(w[4]) >= 6:
                cands.append(pymupdf.Rect(w[0], w[3] - 14, w[2], w[3] - 1))
        for r in cands:
            if any(r.intersects(e) for e in existing):
                continue
            create_field(page, "text", r, unique_name(doc, T('campo_p{}').format(pno + 1)), border_color="")
            existing.append(r)
            n += 1
    return n
